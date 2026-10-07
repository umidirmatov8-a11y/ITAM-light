import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(utc);
dayjs.extend(timezone);
dayjs.extend(relativeTime);

let tz = 'Asia/Tashkent';
let dateFormat = 'DD.MM.YYYY';
let currency = 'UZS';

export const configureFormat = (opts: { timeZone?: string; dateFormat?: string; currency?: string }) => {
  if (opts.timeZone) tz = opts.timeZone;
  if (opts.dateFormat) dateFormat = opts.dateFormat;
  if (opts.currency) currency = opts.currency;
};

export const orgTimeZone = () => tz;
export const defaultCurrency = () => currency;

/** UTC timestamp → organization timezone. */
export const fmtDateTime = (v?: string | null) => (v ? dayjs.utc(v).tz(tz).format(`${dateFormat} HH:mm`) : '');
export const fmtDate = (v?: string | null) => {
  if (!v) return '';
  // DateOnly values come as YYYY-MM-DD and must not be shifted.
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return dayjs(v).format(dateFormat);
  return dayjs.utc(v).tz(tz).format(dateFormat);
};
export const fromNow = (v?: string | null) => (v ? dayjs.utc(v).fromNow() : '');
export const fmtMoney = (v?: number | null, cur?: string | null) =>
  v === undefined || v === null ? '' : `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v)} ${cur ?? currency}`;
export const fmtNumber = (v?: number | null) => (v === undefined || v === null ? '' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(v));
export const fmtSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
};

/** Local picker value (dayjs in org tz) → ISO with offset for the API. */
export const toApiDateTime = (d?: dayjs.Dayjs | null) => (d ? d.tz(tz, true).format() : undefined);
export const toApiDate = (d?: dayjs.Dayjs | null) => (d ? d.format('YYYY-MM-DD') : undefined);
export const nowInTz = () => dayjs().tz(tz);
export const parseDate = (v?: string | null) => (v ? dayjs(v) : null);
export const parseDateTime = (v?: string | null) => (v ? dayjs.utc(v).tz(tz) : null);
export { dayjs };
