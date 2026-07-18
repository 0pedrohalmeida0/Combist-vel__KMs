// engine/index.js — barrel que re-exporta a API pública
import { VEHICLE_PRESETS, listPresets, getPreset } from './presets.js';
import { calculate } from './calculator.js';

export {
  VEHICLE_PRESETS,
  listPresets,
  getPreset,
  calculate,
};
