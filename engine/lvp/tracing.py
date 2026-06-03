"""
tracing.py — optional OpenTelemetry tracing for the pipeline.

Wraps each turn (and each stage: STT, LLM, TTS) in OTel spans so you can ship traces
to Jaeger/Tempo/Honeycomb and see latency breakdowns across a fleet. No-op if
opentelemetry isn't installed — zero overhead, never crashes.

    tracer = get_tracer()             # enabled via LVP_TRACING=true + otel installed
    with tracer.span("stt"):
        ...
"""

import os
from contextlib import contextmanager

TRACING = os.environ.get('LVP_TRACING', 'false').lower() in ('1', 'true', 'yes')


class _NoopTracer:
    @contextmanager
    def span(self, name, **attrs):
        yield None

    def event(self, name, **attrs):
        pass


class _OTelTracer:
    def __init__(self, otel_tracer):
        self._t = otel_tracer

    @contextmanager
    def span(self, name, **attrs):
        with self._t.start_as_current_span(name) as sp:
            for k, v in attrs.items():
                try:
                    sp.set_attribute(k, v)
                except Exception:
                    pass
            yield sp

    def event(self, name, **attrs):
        from opentelemetry import trace
        sp = trace.get_current_span()
        try:
            sp.add_event(name, attributes=attrs)
        except Exception:
            pass


_tracer = None


def get_tracer():
    global _tracer
    if _tracer is not None:
        return _tracer
    if not TRACING:
        _tracer = _NoopTracer()
        return _tracer
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        provider = TracerProvider()
        # Console by default; swap exporter (OTLP → Jaeger/Tempo) via your own setup.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        trace.set_tracer_provider(provider)
        _tracer = _OTelTracer(trace.get_tracer('lvp'))
        print('[tracing] OpenTelemetry enabled', flush=True)
    except ImportError:
        print('[tracing] opentelemetry not installed — tracing disabled', flush=True)
        _tracer = _NoopTracer()
    return _tracer
