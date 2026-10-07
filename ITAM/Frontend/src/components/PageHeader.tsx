import { Breadcrumb, Space, Typography } from 'antd';
import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

export function PageHeader({ title, subtitle, extra, crumbs, tags }: { title: ReactNode; subtitle?: ReactNode; extra?: ReactNode; crumbs?: { title: string; to?: string }[]; tags?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <>
      {crumbs && (
        <Breadcrumb
          style={{ marginBottom: 8 }}
          items={[{ title: <Link to="/">{t('menu.dashboard')}</Link> }, ...crumbs.map((c) => ({ title: c.to ? <Link to={c.to}>{c.title}</Link> : c.title }))]}
        />
      )}
      <div className="itam-page-header">
        <div>
          <Space align="center" wrap>
            <Typography.Title level={3}>{title}</Typography.Title>
            {tags}
          </Space>
          {subtitle && <div className="itam-muted">{subtitle}</div>}
        </div>
        {extra && <Space wrap>{extra}</Space>}
      </div>
    </>
  );
}
