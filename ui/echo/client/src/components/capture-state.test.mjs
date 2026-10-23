import test from 'node:test';
import assert from 'node:assert/strict';
import { captureState } from './capture-state.js';

test('native watching/paused states drive both label and truthful response message', () => {
  for (const [state, expected] of [
    [{ watching: true, paused: false }, { label: 'Vigilando', message: 'Vigilando el portapapeles.' }],
    [{ watching: false, paused: true }, { label: 'En pausa', message: 'Portapapeles en pausa.' }],
    [{ watching: false, paused: false }, { label: 'Captura detenida', message: 'Pausa retirada. La captura sigue detenida.' }],
  ]) assert.deepEqual(captureState(state), expected);
});
