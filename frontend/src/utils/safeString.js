export const safeString = (val) => {
  if (val === null || val === undefined) return "";
  if (typeof val === 'string') return val;
  if (typeof val === 'object') return val.zh_TW || val.tw || val.name || val.label || val.code || "";
  return val.toString();
}

export const normalizeKw = (kw) => kw?.toString().trim().toLowerCase() || '';
