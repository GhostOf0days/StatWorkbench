// SPDX-License-Identifier: MIT
// Independently implemented legacy workbook functions. Currency rounding follows
// the inspected workbook engine's behavior, including its historical quirks.
import { functionDate, NumberValueObject } from '@univerjs/engine-formula';

const RATES = Object.freeze({ ATS:13.7603, BEF:40.3399, DEM:1.95583, ESP:166.386,
  EUR:1, FIM:5.94573, FRF:6.55957, GRD:340.75, IEP:.787564, ITL:1936.27,
  LUX:40.3399, LUF:40.3399, NLG:2.20371, PTE:200.482 });
const WHOLE = new Set(['BEF','ESP','ITL','LUF','LUX']);
const ERRORS = new Set(['#VALUE!','#NUM!','#REF!','#DIV/0!','#N/A','#NAME?','#NULL!']);
const [Yearfrac] = functionDate.find(([, name]) => name === 'YEARFRAC');
const yearfrac = new Yearfrac('YEARFRAC');
const number = value => typeof value === 'number' ? value : typeof value === 'boolean' ? +value
  : value == null || value === '' ? 0 : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
function rounded(value, digits = 0) {
  if (digits >= 15) return value;
  const factor = 10 ** digits, scaled = Math.abs(value) * factor;
  if (!Number.isFinite(scaled)) return value;
  return Math.sign(value) * Math.floor(scaled + .5 + Number.EPSILON * scaled) / factor;
}
function guarded(min, max, fn) {
  return (...args) => {
    if (args.length < min || args.length > max) return '#VALUE!';
    // Single-cell references are scalar; larger ranges have no scalar meaning.
    args = args.map(value => Array.isArray(value) && value.length === 1 &&
      Array.isArray(value[0]) && value[0].length === 1 ? value[0][0] : value);
    const error = args.find(value => ERRORS.has(value));
    if (error) return error;
    if (args.some(value => Array.isArray(value) || (value !== null && typeof value === 'object'))) return '#VALUE!';
    const result = fn(...args);
    return typeof result === 'number' && !Number.isFinite(result) ? '#NUM!' : result;
  };
}
const code = value => typeof value === 'string' ? value.slice(0, 3) : '';

export const isoCeiling = guarded(1, 2, (value, significance = 1) => {
  const n = number(value), step = Math.abs(number(significance));
  if (!Number.isFinite(n) || !Number.isFinite(step)) return '#VALUE!';
  if (!n || !step) return 0;
  const quotient = n / step, nearest = Math.round(quotient);
  return (Math.abs(quotient - nearest) <= Math.abs(quotient) * Number.EPSILON * 2
    ? nearest : Math.ceil(quotient)) * step;
});

export const euro = guarded(1, 1, currency => {
  const rate = RATES[code(currency)];
  return rate === undefined ? '#NUM!' : rounded(rate, 2);
});

export const euroConvert = guarded(3, 5, (value, source, target, fullPrecision = false, triangulationPrecision) => {
  const n = number(value), from = code(source), to = code(target);
  if (!Number.isFinite(n) || RATES[from] === undefined || RATES[to] === undefined) return '#VALUE!';
  let full = fullPrecision;
  if (typeof full === 'string') {
    if (!/^(true|false)$/i.test(full)) return '#VALUE!';
    full = /^true$/i.test(full);
  }
  if (typeof full !== 'boolean' && !Number.isFinite(number(full))) return '#VALUE!';
  let digits = WHOLE.has(from) ? 0 : from === 'PTE' ? 1 : 2;
  if (triangulationPrecision !== undefined && triangulationPrecision !== null) {
    digits = Math.trunc(number(triangulationPrecision));
    if (!Number.isFinite(digits) || digits < 3) return '#VALUE!';
  }
  if (from === to) return n;
  const result = n / rounded(RATES[from], digits) * rounded(RATES[to], digits);
  return full ? result : rounded(result, WHOLE.has(to) ? 0 : 2);
});

export const amorDegrc = guarded(6, 7, (cost, purchased, firstPeriod, salvage, period, rate, basis = 0) => {
  [cost, purchased, firstPeriod, salvage, period, rate, basis] =
    [cost, purchased, firstPeriod, salvage, period, rate, basis].map(number);
  if (![cost, purchased, firstPeriod, salvage, period, rate, basis].every(Number.isFinite)) return '#VALUE!';
  purchased = Math.trunc(purchased); firstPeriod = Math.trunc(firstPeriod);
  period = Math.trunc(period); basis = Math.trunc(basis);
  if (cost < 0 || salvage < 0 || salvage > cost || purchased < 0 || firstPeriod < purchased ||
      firstPeriod > 2958465 || period < 0 || period > 100000 || rate <= 0 || ![0,1,3,4].includes(basis)) return '#NUM!';
  const life = 1 / rate;
  if ((life > 0 && life < 1) || (life > 1 && life < 2) || (life > 2 && life < 3) || (life > 4 && life < 5)) return '#NUM!';
  const factor = life < 3 ? 1 : life < 5 ? 1.5 : life <= 6 ? 2 : 2.5;
  const adjusted = rate * factor;
  const fraction = yearfrac.calculate(...[purchased, firstPeriod, basis].map(value => NumberValueObject.create(value)));
  if (fraction.isError()) return fraction.getValue();
  let depreciation = rounded(cost * adjusted * fraction.getValue());
  if (period === 0) return depreciation;
  let remaining = cost - depreciation, allowance = remaining - salvage;
  for (let index = 0; index < period; index++) {
    depreciation = rounded(remaining * adjusted);
    allowance -= depreciation;
    if (allowance < 0) return period - index <= 1 ? rounded(remaining / 2) : 0;
    remaining -= depreciation;
    if (depreciation === 0) return 0;
  }
  return depreciation;
});

// One calculation supplies the entire legacy result rectangle. This avoids
// evaluating RAND/NOW separately for each projected output cell.
export function legacyArray(value, height, width) {
  height = number(height); width = number(width);
  if (!Number.isInteger(height) || !Number.isInteger(width) || height < 1 || width < 1 ||
      height > 100000 || width > 1000 || height * width > 2000000) return '#NUM!';
  const input = Array.isArray(value) ? value : [[value]];
  if (!input.length || input.some(row => !Array.isArray(row) || row.length !== input[0].length) || !input[0].length) return '#VALUE!';
  return Array.from({length:height}, (_, r) => Array.from({length:width}, (_, c) => {
    const row = input.length === 1 ? 0 : r, column = input[0].length === 1 ? 0 : c;
    return row < input.length && column < input[0].length ? input[row][column] ?? 0 : '#N/A';
  }));
}

export function registerLegacyFunctions(univerAPI) {
  const engine = univerAPI.getFormula();
  const registrations = Object.entries({ 'ISO.CEILING':isoCeiling, EURO:euro,
    EUROCONVERT:euroConvert, AMORDEGRC:amorDegrc, 'SWB.CSE':legacyArray }).map(([name, fn]) => engine.registerFunction(name, fn));
  return { dispose() { registrations.splice(0).forEach(item => item.dispose()); } };
}
