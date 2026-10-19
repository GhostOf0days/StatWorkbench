// Presentation metadata is kept separate from the numerical field schema.
export function orderedFields(fields, layout = {}) {
  return fields.map((field, index) => ({field, index})).sort((a, b) =>
    (layout[a.field.key]?.order ?? 10000 + a.index) - (layout[b.field.key]?.order ?? 10000 + b.index)
  ).map(({field}) => field);
}

export function controlEnabled(key, options, layout = {}, visited = new Set()) {
  const info = layout[key];
  if (!info?.parent) return true;
  if (visited.has(key)) throw new Error('Invalid circular option dependency.');
  const next = new Set(visited).add(key);
  if (!controlEnabled(info.parent, options, layout, next)) return false;
  const value = options[info.parent];
  const enabled = value !== false && value !== 0 && value !== '0' && value !== '' && value !== 'false' && value !== null && value !== undefined;
  return info.parentInverse ? !enabled : enabled;
}

export function numericOptionError(field, value, layout = {}) {
  if (value === '' || value === null || value === undefined) return field.required ? `${field.label} is required.` : null;
  // Cell references are validated and resolved against computed worksheet values later.
  if (layout.cellReference && typeof value === 'string' && !Number.isFinite(Number(value))) return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return `${field.label} must be a finite number.`;
  if (field.type === 'integer' && !Number.isInteger(number)) return `${field.label} must be an integer.`;
  if (field.min !== undefined && number < field.min) return `${field.label} must be at least ${field.min}.`;
  if (field.max !== undefined && number > field.max) return `${field.label} must be at most ${field.max}.`;
  const validator = layout.validator;
  if (validator && validator !== 'numbernullable') {
    const valid = validator.split(',').some(part => {
      const match = part.match(/^(\d+)(?:-(\d*)?)?$/);
      if (!match) return false;
      return part.includes('-') ? number >= Number(match[1]) && (!match[2] || number <= Number(match[2])) : number === Number(match[1]);
    });
    if (!valid) return `${field.label} is outside the permitted values (${validator}).`;
  }
  return null;
}
