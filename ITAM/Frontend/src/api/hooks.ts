import { useQuery, useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import { get, ApiError } from './client';
import type { CustomFieldDef, CustomFieldEntity, LookupItem } from './types';

/** Active dictionary items for dropdowns. */
export const useLookup = (key: string, enabled = true) =>
  useQuery<LookupItem[]>({ queryKey: ['lookup-options', key], queryFn: () => get(`/lookups/${key}/options`), staleTime: 5 * 60_000, enabled });

export const useCustomFields = (entity: CustomFieldEntity, assetTypeId?: string) =>
  useQuery<CustomFieldDef[]>({
    queryKey: ['custom-fields', entity, assetTypeId ?? null],
    queryFn: () => get('/custom-fields', { entity, assetTypeId }),
    staleTime: 5 * 60_000,
  });

/** Shows backend error messages (translated envelope messages come from the server). */
export function useNotify() {
  const { message, notification } = App.useApp();
  const { t } = useTranslation();
  return {
    success: (text?: string) => message.success(text ?? t('common.saved')),
    error: (e: unknown) => {
      if (e instanceof ApiError) {
        const details = e.details && typeof e.details === 'object' && !Array.isArray(e.details)
          ? Object.entries(e.details as Record<string, unknown>)
              .filter(([, v]) => Array.isArray(v))
              .map(([k, v]) => `${k}: ${(v as string[]).join(', ')}`)
              .join('\n')
          : '';
        notification.error({ message: t(`errors.${e.code}`, { defaultValue: t('errors.generic') }), description: [e.message, details].filter(Boolean).join('\n'), duration: 8 });
      } else notification.error({ message: t('errors.generic'), description: String(e) });
    },
  };
}

/** Mutation with toast + cache invalidation. */
export function useApiMutation<TVars, TResult = unknown>(fn: (v: TVars) => Promise<TResult>, opts?: { invalidate?: QueryKey[]; success?: string | false; onSuccess?: (r: TResult, v: TVars) => void }) {
  const qc = useQueryClient();
  const notify = useNotify();
  return useMutation<TResult, unknown, TVars>({
    mutationFn: fn,
    onSuccess: (r, v) => {
      opts?.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      if (opts?.success !== false) notify.success(opts?.success);
      opts?.onSuccess?.(r, v);
    },
    onError: (e) => notify.error(e),
  });
}
