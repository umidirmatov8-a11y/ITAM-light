import { NextFunction, Request, Response } from 'express';
import { z, ZodType } from 'zod';

export class HttpError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

export const badRequest = (m: string, d?: unknown) => new HttpError(400, m, d);
export const notFound = (m = 'Объект не найден') => new HttpError(404, m);
export const forbidden = (m = 'Недостаточно прав') => new HttpError(403, m);
export const conflict = (m: string) => new HttpError(409, m);

export function parse<T extends ZodType>(schema: T, data: unknown): z.infer<T> {
  const r = schema.safeParse(data);
  if (!r.success) {
    const msg = r.error.issues.map((i) => `${i.path.join('.') || 'значение'}: ${i.message}`).join('; ');
    throw badRequest(`Ошибка валидации: ${msg}`, r.error.issues);
  }
  return r.data;
}

export function errorHandler(err: any, _req: Request, res: Response, _next: NextFunction) {
  if (err instanceof HttpError) {
    res.status(err.status).json({ error: err.message, details: err.details });
    return;
  }
  if (err?.code === '23505') { res.status(409).json({ error: 'Запись с такими значениями уже существует' }); return; }
  if (err?.code === '23503') { res.status(409).json({ error: 'Операция нарушает ссылочную целостность: запись используется другими данными или ссылается на несуществующую' }); return; }
  if (err?.code === 'P0001') { res.status(409).json({ error: err.message }); return; }
  if (err?.code === '22P02') { res.status(400).json({ error: 'Некорректный формат идентификатора или значения' }); return; }
  if (err?.code === 'LIMIT_FILE_SIZE') { res.status(413).json({ error: 'Файл превышает допустимый размер' }); return; }
  if (err?.type === 'entity.too.large') { res.status(413).json({ error: 'Слишком большой запрос' }); return; }
  console.error(err);
  res.status(500).json({ error: 'Внутренняя ошибка сервера' });
}

// Часто используемые схемы.
export const zId = z.string().uuid();
export const zDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'ожидается дата ГГГГ-ММ-ДД');
export const zOptDate = z.union([zDate, z.literal(''), z.null()]).optional().transform((v) => (v ? v : null));
export const zOptId = z.union([zId, z.literal(''), z.null()]).optional().transform((v) => (v ? v : null));
export const zOptText = z.union([z.string(), z.null()]).optional().transform((v) => (v && v.trim() ? v.trim() : null));
export const zText = z.string().trim().min(1, 'обязательное поле');
export const zRisk = z.enum(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']);
