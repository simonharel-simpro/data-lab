import { z } from 'astro/zod';
import { isValidName } from './name.ts';

export const STATUSES = ['idée', 'en cours', 'conclu', 'abandonné'] as const;
export type Status = (typeof STATUSES)[number];

// The key is interpolated into an MLflow `order_by` between backticks (F-7): no backtick, quote or space.
export const METRIC_KEY_RE = /^[A-Za-z0-9_.\-/]+$/;

export const metricSchema = z.object({
  key: z.string().regex(METRIC_KEY_RE, { message: 'metric.key may only contain letters, digits and _ . - /' }),
  goal: z.enum(['max', 'min']),
});
export type Metric = z.infer<typeof metricSchema>;

export const cardSchema = z.object({
  name: z.string().refine(isValidName, { message: 'name must match NAME_RE and not be a reserved word' }),
  title: z.string(),
  // NFC so a status typed in NFD (`idée`) still matches (G-9).
  status: z.preprocess((s) => (typeof s === 'string' ? s.normalize('NFC').trim() : s), z.enum(STATUSES)),
  tags: z.array(z.string()).default([]),
  data: z.string().optional(),
  metric: metricSchema.optional(),
});
export type Card = z.infer<typeof cardSchema>;
