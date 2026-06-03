/**
 * @logica-voice/client — talk to a live Logica Voice pipeline over WebSocket.
 *
 * Core (browser + Node):
 *   import { LogicaVoiceClient } from '@logica-voice/client';
 * Browser audio helpers (mic + speaker):
 *   import { startMicrophone, createPlayer } from '@logica-voice/client/browser';
 */

export { LogicaVoiceClient } from './client.js';
export type { VoiceClientEvents, VoiceClientOptions } from './client.js';
export * from './protocol.js';
