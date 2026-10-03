import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { Result, Spin, Button } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from './auth';
import { get, onApiError } from '@/api/client';
import MainLayout from '@/layouts/MainLayout';

const LoginPage = lazy(() => import('@/pages/misc/LoginPage'));
const SetupPage = lazy(() => import('@/pages/misc/SetupPage'));
const ChangePasswordPage = lazy(() => import('@/pages/misc/ChangePasswordPage'));
const ProfilePage = lazy(() => import('@/pages/misc/ProfilePage'));
const DashboardPage = lazy(() => import('@/pages/misc/DashboardPage'));
const SearchPage = lazy(() => import('@/pages/misc/SearchPage'));
const NotificationsPage = lazy(() => import('@/pages/misc/NotificationsPage'));
const PublicAssetPage = lazy(() => import('@/pages/misc/PublicAssetPage'));
const EmployeesPage = lazy(() => import('@/pages/employees/EmployeesPage'));
const EmployeeCard = lazy(() => import('@/pages/employees/EmployeeCard'));
const AssetsPage = lazy(() => import('@/pages/assets/AssetsPage'));
const AssetCard = lazy(() => import('@/pages/assets/AssetCard'));
const RepairsPage = lazy(() => import('@/pages/assets/RepairsPage'));
const RepairCard = lazy(() => import('@/pages/assets/RepairCard'));
const OperationsPage = lazy(() => import('@/pages/operations/OperationsPage'));
const OperationCard = lazy(() => import('@/pages/operations/OperationCard'));
const IssuePage = lazy(() => import('@/pages/operations/IssuePage'));
const ReturnPage = lazy(() => import('@/pages/operations/ReturnPage'));
const TransferPage = lazy(() => import('@/pages/operations/TransferPage'));
const StatusChangePage = lazy(() => import('@/pages/operations/StatusChangePage'));
const LicensesPage = lazy(() => import('@/pages/licenses/LicensesPage'));
const LicenseCard = lazy(() => import('@/pages/licenses/LicenseCard'));
const SoftwarePage = lazy(() => import('@/pages/licenses/SoftwarePage'));
const AccessPage = lazy(() => import('@/pages/access/AccessPage'));
const ChecklistsPage = lazy(() => import('@/pages/checklists/ChecklistsPage'));
const ChecklistCard = lazy(() => import('@/pages/checklists/ChecklistCard'));
const DocumentsPage = lazy(() => import('@/pages/documents/DocumentsPage'));
const ReportsPage = lazy(() => import('@/pages/reports/ReportsPage'));
const ImportPage = lazy(() => import('@/pages/reports/ImportPage'));
const InventoryPage = lazy(() => import('@/pages/inventory/InventoryPage'));
const InventoryCard = lazy(() => import('@/pages/inventory/InventoryCard'));
const StockPage = lazy(() => import('@/pages/inventory/StockPage'));
const ContractsPage = lazy(() => import('@/pages/inventory/ContractsPage'));
const DictionariesPage = lazy(() => import('@/pages/admin/DictionariesPage'));
const CustomFieldsPage = lazy(() => import('@/pages/admin/CustomFieldsPage'));
const TemplatesPage = lazy(() => import('@/pages/admin/TemplatesPage'));
const TemplateCard = lazy(() => import('@/pages/admin/TemplateCard'));
const ChecklistTemplatesPage = lazy(() => import('@/pages/admin/ChecklistTemplatesPage'));
const UsersPage = lazy(() => import('@/pages/admin/UsersPage'));
const RolesPage = lazy(() => import('@/pages/admin/RolesPage'));
const AuditPage = lazy(() => import('@/pages/admin/AuditPage'));
const SettingsPage = lazy(() => import('@/pages/admin/SettingsPage'));
const BackupPage = lazy(() => import('@/pages/admin/BackupPage'));
const SystemPage = lazy(() => import('@/pages/admin/SystemPage'));

const Loading = () => (
  <div style={{ display: 'grid', placeItems: 'center', minHeight: '60vh' }}>
    <Spin size="large" />
  </div>
);

interface PublicInfo { organizationName: string; version: string; setupCompleted: boolean; qrPublicView: boolean }

function Guard({ perm, children }: { perm?: string; children: ReactNode }) {
  const { can } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  if (perm && !can(perm))
    return <Result status="403" title="403" subTitle={t('errors.FORBIDDEN')} extra={<Button onClick={() => navigate('/')}>{t('common.toHome')}</Button>} />;
  return <>{children}</>;
}

function AssetRoute() {
  const { me } = useAuth();
  const { id } = useParams();
  return me ? <AssetCard key={id} /> : <PublicAssetPage />;
}

export default function App() {
  const { me, loading } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const info = useQuery<PublicInfo>({ queryKey: ['public-info'], queryFn: () => get('/public/info'), staleTime: 60_000 });

  useEffect(
    () =>
      onApiError((e) => {
        if (e.status === 401 && !location.pathname.startsWith('/login') && !location.pathname.startsWith('/setup')) {
          qc.setQueryData(['me'], null);
        }
        if (e.code === 'PASSWORD_CHANGE_REQUIRED') navigate('/change-password');
      }),
    [location.pathname, navigate, qc],
  );

  if (loading || info.isLoading) return <Loading />;
  const setupDone = info.data?.setupCompleted ?? true;
  const path = location.pathname;

  if (!setupDone && !path.startsWith('/setup')) return <Navigate to="/setup" replace />;

  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route path="/setup" element={setupDone ? <Navigate to="/" replace /> : <SetupPage />} />
        <Route path="/login" element={me ? <Navigate to={new URLSearchParams(location.search).get('next') || '/'} replace /> : <LoginPage />} />
        <Route path="/change-password" element={me ? <ChangePasswordPage /> : <Navigate to="/login" replace />} />
        {!me && <Route path="/assets/:id" element={<PublicAssetPage />} />}
        {!me && <Route path="*" element={<Navigate to={`/login?next=${encodeURIComponent(path + location.search)}`} replace />} />}
        {me && me.mustChangePassword && <Route path="*" element={<Navigate to="/change-password" replace />} />}
        {me && (
          <Route element={<MainLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="notifications" element={<NotificationsPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="employees" element={<Guard perm="employees.view"><EmployeesPage /></Guard>} />
            <Route path="employees/:id" element={<Guard perm="employees.view"><EmployeeCard /></Guard>} />
            <Route path="assets" element={<Guard perm="assets.view"><AssetsPage /></Guard>} />
            <Route path="assets/:id" element={<Guard perm="assets.view"><AssetRoute /></Guard>} />
            <Route path="repairs" element={<Guard perm="assets.view"><RepairsPage /></Guard>} />
            <Route path="repairs/:id" element={<Guard perm="assets.view"><RepairCard /></Guard>} />
            <Route path="operations" element={<Guard perm="assets.view"><OperationsPage /></Guard>} />
            <Route path="operations/issue" element={<Guard perm="assets.assign"><IssuePage /></Guard>} />
            <Route path="operations/return" element={<Guard perm="assets.return"><ReturnPage /></Guard>} />
            <Route path="operations/transfer" element={<Guard perm="assets.transfer"><TransferPage /></Guard>} />
            <Route path="operations/status" element={<Guard perm="assets.status"><StatusChangePage /></Guard>} />
            <Route path="operations/:id" element={<Guard perm="assets.view"><OperationCard /></Guard>} />
            <Route path="licenses" element={<Guard perm="licenses.view"><LicensesPage /></Guard>} />
            <Route path="licenses/:id" element={<Guard perm="licenses.view"><LicenseCard /></Guard>} />
            <Route path="software" element={<Guard perm="software.view"><SoftwarePage /></Guard>} />
            <Route path="access" element={<Guard perm="access.view"><AccessPage /></Guard>} />
            <Route path="onboarding" element={<Guard perm="checklists.view"><ChecklistsPage kind="Onboarding" /></Guard>} />
            <Route path="offboarding" element={<Guard perm="checklists.view"><ChecklistsPage kind="Offboarding" /></Guard>} />
            <Route path="checklists/:id" element={<Guard perm="checklists.view"><ChecklistCard /></Guard>} />
            <Route path="documents" element={<Guard perm="documents.view"><DocumentsPage /></Guard>} />
            <Route path="contracts" element={<Guard perm="contracts.view"><ContractsPage /></Guard>} />
            <Route path="reports" element={<Guard perm="reports.view"><ReportsPage /></Guard>} />
            <Route path="import" element={<Guard perm="import.run"><ImportPage /></Guard>} />
            <Route path="inventory" element={<Guard perm="inventory.view"><InventoryPage /></Guard>} />
            <Route path="inventory/:id" element={<Guard perm="inventory.view"><InventoryCard /></Guard>} />
            <Route path="stock" element={<Guard perm="stock.view"><StockPage /></Guard>} />
            <Route path="admin/dictionaries" element={<DictionariesPage />} />
            <Route path="admin/dictionaries/:key" element={<DictionariesPage />} />
            <Route path="admin/custom-fields" element={<Guard perm="customfields.manage"><CustomFieldsPage /></Guard>} />
            <Route path="admin/templates" element={<Guard perm="documents.view"><TemplatesPage /></Guard>} />
            <Route path="admin/templates/:id" element={<Guard perm="documents.view"><TemplateCard /></Guard>} />
            <Route path="admin/checklist-templates" element={<Guard perm="checklists.templates.manage"><ChecklistTemplatesPage /></Guard>} />
            <Route path="admin/users" element={<Guard perm="users.manage"><UsersPage /></Guard>} />
            <Route path="admin/roles" element={<Guard perm="roles.manage"><RolesPage /></Guard>} />
            <Route path="admin/audit" element={<Guard perm="audit.view"><AuditPage /></Guard>} />
            <Route path="admin/settings" element={<Guard perm="settings.manage"><SettingsPage /></Guard>} />
            <Route path="admin/backup" element={<Guard perm="backup.manage"><BackupPage /></Guard>} />
            <Route path="admin/system" element={<Guard perm="settings.manage"><SystemPage /></Guard>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        )}
      </Routes>
    </Suspense>
  );
}

function NotFound() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return <Result status="404" title="404" subTitle={t('errors.NOT_FOUND')} extra={<Button onClick={() => navigate('/')}>{t('common.toHome')}</Button>} />;
}
