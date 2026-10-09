import { useMemo, useState } from 'react';
import { Avatar, Badge, Button, Dropdown, Input, Layout, Menu, Select, Space, Tooltip, theme } from 'antd';
import {
  AppstoreOutlined, AuditOutlined, BarChartOutlined, BellOutlined, CloudServerOutlined, ContainerOutlined, DashboardOutlined, DatabaseOutlined,
  FileTextOutlined, ImportOutlined, InboxOutlined, KeyOutlined, LaptopOutlined, LogoutOutlined, MoonOutlined, PlusOutlined, ProfileOutlined,
  SafetyCertificateOutlined, ScanOutlined, SettingOutlined, SolutionOutlined, SunOutlined, SwapOutlined, TeamOutlined, ToolOutlined, UserOutlined, DesktopOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/app/auth';
import { useThemeMode } from '@/theme/theme';
import { get } from '@/api/client';
import { LANGUAGES, setLanguage } from '@/i18n';

const { Sider, Header, Content } = Layout;

export default function MainLayout() {
  const { t, i18n } = useTranslation();
  const { me, can, canAny, logout } = useAuth();
  const { mode, toggle } = useThemeMode();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('itam.sider') === '1');
  const { token } = theme.useToken();

  const unread = useQuery<{ count: number }>({ queryKey: ['notifications-unread'], queryFn: () => get('/notifications/unread-count'), refetchInterval: 60_000 });

  const items = useMemo(() => {
    type Item = Required<MenuProps>['items'][number];
    const it = (key: string, icon: React.ReactNode, label: string, show = true): Item | null => (show ? { key, icon, label } : null);
    const admin = [
      it('/admin/dictionaries', <DatabaseOutlined />, t('menu.dictionaries'), canAny('dictionaries.manage', 'org.manage', 'org.view')),
      it('/admin/custom-fields', <AppstoreOutlined />, t('menu.customFields'), can('customfields.manage')),
      it('/admin/templates', <FileTextOutlined />, t('menu.templates'), can('documents.templates.manage')),
      it('/admin/checklist-templates', <ProfileOutlined />, t('menu.checklistTemplates'), can('checklists.templates.manage')),
      it('/admin/users', <UserOutlined />, t('menu.users'), can('users.manage')),
      it('/admin/roles', <SafetyCertificateOutlined />, t('menu.roles'), can('roles.manage')),
      it('/admin/audit', <AuditOutlined />, t('menu.audit'), can('audit.view')),
      it('/admin/settings', <SettingOutlined />, t('menu.settings'), can('settings.manage')),
      it('/admin/backup', <CloudServerOutlined />, t('menu.backup'), can('backup.manage')),
      it('/admin/system', <DashboardOutlined />, t('menu.system'), can('settings.manage')),
    ].filter(Boolean) as Item[];
    return [
      it('/', <DashboardOutlined />, t('menu.dashboard')),
      it('/employees', <TeamOutlined />, t('menu.employees'), can('employees.view')),
      can('assets.view')
        ? {
            key: 'assets-group', icon: <LaptopOutlined />, label: t('menu.assetsGroup'),
            children: [
              it('/assets', <LaptopOutlined />, t('menu.assets')),
              it('/operations', <SwapOutlined />, t('menu.operations')),
              it('/repairs', <ToolOutlined />, t('menu.repairs')),
              it('/inventory', <ScanOutlined />, t('menu.inventory'), can('inventory.view')),
              it('/stock', <InboxOutlined />, t('menu.stock'), can('stock.view')),
              it('/agents', <DesktopOutlined />, t('menu.agents'), can('agents.view')),
            ].filter(Boolean) as Item[],
          }
        : null,
      canAny('licenses.view', 'software.view')
        ? {
            key: 'lic-group', icon: <KeyOutlined />, label: t('menu.licensesGroup'),
            children: [it('/licenses', <KeyOutlined />, t('menu.licenses'), can('licenses.view')), it('/software', <AppstoreOutlined />, t('menu.software'), can('software.view'))].filter(Boolean) as Item[],
          }
        : null,
      it('/access', <SafetyCertificateOutlined />, t('menu.access'), can('access.view')),
      can('checklists.view')
        ? {
            key: 'lifecycle', icon: <SolutionOutlined />, label: t('menu.lifecycle'),
            children: [it('/onboarding', <SolutionOutlined />, t('menu.onboarding')), it('/offboarding', <SolutionOutlined />, t('menu.offboarding'))].filter(Boolean) as Item[],
          }
        : null,
      it('/documents', <FileTextOutlined />, t('menu.documents'), can('documents.view')),
      it('/contracts', <ContainerOutlined />, t('menu.contracts'), can('contracts.view')),
      it('/reports', <BarChartOutlined />, t('menu.reports'), can('reports.view')),
      it('/import', <ImportOutlined />, t('menu.import'), can('import.run')),
      admin.length ? { key: 'admin', icon: <SettingOutlined />, label: t('menu.admin'), children: admin } : null,
    ].filter(Boolean) as Item[];
  }, [t, can, canAny]);

  const selected = useMemo(() => {
    const p = location.pathname;
    const keys = ['/admin/dictionaries', '/admin/custom-fields', '/admin/templates', '/admin/checklist-templates', '/admin/users', '/admin/roles', '/admin/audit',
      '/admin/settings', '/admin/backup', '/admin/system', '/employees', '/assets', '/operations', '/repairs', '/inventory', '/stock', '/agents', '/licenses', '/software',
      '/access', '/onboarding', '/offboarding', '/documents', '/contracts', '/reports', '/import'];
    return [keys.find((k) => p.startsWith(k)) ?? '/'];
  }, [location.pathname]);

  const quick: MenuProps['items'] = [
    can('employees.create') && { key: 'emp', label: t('quick.addEmployee'), onClick: () => navigate('/employees?new=1') },
    can('assets.create') && { key: 'asset', label: t('quick.addAsset'), onClick: () => navigate('/assets?new=1') },
    can('assets.assign') && { key: 'issue', label: t('quick.issue'), onClick: () => navigate('/operations/issue') },
    can('assets.return') && { key: 'return', label: t('quick.return'), onClick: () => navigate('/operations/return') },
    can('assets.transfer') && { key: 'transfer', label: t('quick.transfer'), onClick: () => navigate('/operations/transfer') },
    can('assets.repair') && { key: 'repair', label: t('quick.repair'), onClick: () => navigate('/repairs?new=1') },
    can('documents.generate') && { key: 'doc', label: t('quick.document'), onClick: () => navigate('/operations') },
  ].filter(Boolean) as MenuProps['items'];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={(c) => { setCollapsed(c); localStorage.setItem('itam.sider', c ? '1' : '0'); }}
        width={248}
        breakpoint="lg"
        style={{ position: 'sticky', top: 0, height: '100vh', overflow: 'auto' }}
        className="itam-no-print"
      >
        <div className="itam-logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
          <span className="itam-logo-mark">IT</span>
          {!collapsed && <span>{me?.organizationName || 'ITAM'}</span>}
        </div>
        <Menu theme="dark" mode="inline" items={items} selectedKeys={selected} defaultOpenKeys={['assets-group']} onClick={(e) => navigate(e.key)} />
      </Sider>
      <Layout>
        <Header className="itam-header" style={{ background: token.colorBgContainer }}>
          <Input.Search
            placeholder={t('header.searchPlaceholder')}
            allowClear
            style={{ maxWidth: 460 }}
            onSearch={(q) => q.trim() && navigate(`/search?q=${encodeURIComponent(q.trim())}`)}
          />
          <div style={{ flex: 1 }} />
          {quick && quick.length > 0 && (
            <Dropdown menu={{ items: quick }}>
              <Button type="primary" icon={<PlusOutlined />}>{t('header.quickActions')}</Button>
            </Dropdown>
          )}
          <Tooltip title={t('menu.notifications')}>
            <Badge count={unread.data?.count ?? 0} size="small" overflowCount={99}>
              <Button shape="circle" icon={<BellOutlined />} onClick={() => navigate('/notifications')} />
            </Badge>
          </Tooltip>
          <Tooltip title={mode === 'dark' ? t('header.lightTheme') : t('header.darkTheme')}>
            <Button shape="circle" icon={mode === 'dark' ? <SunOutlined /> : <MoonOutlined />} onClick={toggle} />
          </Tooltip>
          <Select size="middle" value={i18n.language} style={{ width: 120 }} onChange={setLanguage} options={LANGUAGES.map((l) => ({ value: l.code, label: l.label }))} />
          <Dropdown
            menu={{
              items: [
                { key: 'profile', icon: <UserOutlined />, label: t('header.profile'), onClick: () => navigate('/profile') },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: t('header.logout'), onClick: logout },
              ],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar style={{ background: '#1d4ed8' }}>{me?.displayName?.[0] ?? '?'}</Avatar>
              <span>{me?.displayName}</span>
            </Space>
          </Dropdown>
        </Header>
        <Content className="itam-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
