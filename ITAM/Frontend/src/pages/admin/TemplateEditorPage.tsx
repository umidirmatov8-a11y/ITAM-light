import { Alert, App, Button, Card, Checkbox, Col, Dropdown, Empty, Form, Input, InputNumber, Modal, Row, Segmented, Select, Skeleton, Space, Tabs, Tooltip, Typography } from 'antd';
import {
  AlignCenterOutlined, AlignLeftOutlined, AlignRightOutlined, ArrowDownOutlined, ArrowUpOutlined, BoldOutlined, CopyOutlined, DeleteOutlined,
  EyeOutlined, ItalicOutlined, MenuOutlined, PlusOutlined, SaveOutlined, UnderlineOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, get, post } from '@/api/client';
import { useApiMutation, useNotify } from '@/api/hooks';
import { PageHeader } from '@/components/PageHeader';
import { EnumSelect } from '@/components/Selects';
import { DOCUMENT_TYPES } from '@/utils/enums';

type BlockType = 'heading' | 'paragraph' | 'table' | 'signatures' | 'empty' | 'pageBreak';
type Align = 'left' | 'center' | 'right' | 'both';
export interface Block {
  type: BlockType; text?: string; bold?: boolean; italic?: boolean; underline?: boolean; align?: Align | null; fontSize?: number | null;
  rows?: string[][]; headerRow?: boolean; boldFirstColumn?: boolean; borders?: boolean; columnWidths?: number[] | null;
}
interface Model { blocks: Block[] }
interface Placeholder { key: string; description: string }
interface EditorDto { templateId: string; name: string; documentType: string; versionId?: string; versionNumber?: number; model: Model; fromDocx: boolean; availablePlaceholders: Placeholder[] }
interface TplListItem { id: string; name: string; documentType: string; isDefault: boolean; isArchived: boolean }

/** Last focused text field: where a placeholder is inserted. */
interface Focus { block: number; row?: number; col?: number; el: HTMLTextAreaElement | HTMLInputElement }

const ITEM_TABLE: Block = {
  type: 'table', headerRow: true, borders: true, columnWidths: [6, 18, 32, 22, 22],
  rows: [['№', 'Инв. номер', 'Наименование', 'Производитель / модель', 'Серийный номер'],
    ['{{Item.Index}}', '{{Item.InventoryNumber}}', '{{Item.Name}}', '{{Item.Manufacturer}} {{Item.Model}}', '{{Item.SerialNumber}}']],
};

const PRESETS: { key: string; block: () => Block }[] = [
  { key: 'heading', block: () => ({ type: 'heading', text: 'ЗАГОЛОВОК' }) },
  { key: 'paragraph', block: () => ({ type: 'paragraph', text: '' }) },
  { key: 'itemsTable', block: () => structuredClone(ITEM_TABLE) },
  { key: 'keyValue', block: () => ({ type: 'table', boldFirstColumn: true, borders: false, columnWidths: [35, 65], rows: [['Сотрудник', '{{Employee.FullName}}'], ['Должность', '{{Employee.Position}}']] }) },
  { key: 'table', block: () => ({ type: 'table', headerRow: true, borders: true, rows: [['', ''], ['', '']] }) },
  { key: 'signatures', block: () => ({ type: 'signatures', rows: [['Выдал:', '{{Responsible.ShortName}}'], ['Получил:', '{{Employee.ShortName}}']] }) },
  { key: 'empty', block: () => ({ type: 'empty' }) },
  { key: 'pageBreak', block: () => ({ type: 'pageBreak' }) },
];

const blankModel = (): Model => ({
  blocks: [
    { type: 'paragraph', text: '{{Organization.Name}}', bold: true, align: 'center' },
    { type: 'heading', text: 'НАЗВАНИЕ ДОКУМЕНТА' },
    { type: 'paragraph', text: '№ {{Document.Number}} от {{Document.Date}}', align: 'center' },
    { type: 'empty' },
    { type: 'paragraph', text: '' },
  ],
});

const PLACEHOLDER_RE = /(\{\{\s*[A-Za-z0-9_.<>а-яё]+\s*\}\})/gi;
const IS_PLACEHOLDER = /^\{\{.*\}\}$/;

/** Text with highlighted {{placeholders}} for the live preview. */
function Rich({ text }: { text?: string }) {
  return <>{(text ?? '').split(PLACEHOLDER_RE).map((part, i) => (IS_PLACEHOLDER.test(part) ? <mark key={i} className="itam-ph">{part}</mark> : <Fragment key={i}>{part}</Fragment>))}</>;
}

const textStyle = (b: Block, base: number): React.CSSProperties => ({
  fontWeight: b.type === 'heading' || b.bold ? 700 : 400, fontStyle: b.italic ? 'italic' : undefined, textDecoration: b.underline ? 'underline' : undefined,
  textAlign: (b.align ?? (b.type === 'heading' ? 'center' : 'left')) === 'both' ? 'justify' : ((b.align ?? (b.type === 'heading' ? 'center' : 'left')) as React.CSSProperties['textAlign']),
  fontSize: `${(b.fontSize ?? base) * 1.25}px`, whiteSpace: 'pre-wrap', fontFamily: '"Times New Roman", Times, serif',
});

/** A4-like live preview of the model. */
function Preview({ model }: { model: Model }) {
  const { t } = useTranslation();
  return (
    <div className="itam-paper">
      {model.blocks.map((b, i) => {
        switch (b.type) {
          case 'heading': return <div key={i} style={{ ...textStyle(b, 14), marginBottom: 12 }}><Rich text={b.text} /></div>;
          case 'paragraph': return <div key={i} style={{ ...textStyle(b, 11), marginBottom: 4, minHeight: '1.2em' }}><Rich text={b.text} /></div>;
          case 'empty': return <div key={i} style={{ height: '1.2em' }} />;
          case 'pageBreak': return <div key={i} className="itam-pagebreak">{t('templateEditor.block.pageBreak')}</div>;
          case 'signatures': return (
            <table key={i} className="itam-paper-table" style={{ border: 'none' }}><tbody>
              {(b.rows ?? []).map((r, ri) => <tr key={ri}><td style={{ border: 'none', fontWeight: 700 }}><Rich text={r[0]} /></td><td style={{ border: 'none' }}>____________________</td><td style={{ border: 'none' }}><Rich text={r[1]} /></td></tr>)}
            </tbody></table>
          );
          case 'table': {
            const widths = b.columnWidths;
            return (
              <table key={i} className={`itam-paper-table${b.borders === false ? ' itam-paper-table-plain' : ''}`} style={{ fontSize: `${(b.fontSize ?? 10) * 1.25}px` }}>
                {widths && <colgroup>{widths.map((w, wi) => <col key={wi} style={{ width: `${w}%` }} />)}</colgroup>}
                <tbody>{(b.rows ?? []).map((r, ri) => {
                  const repeated = r.some((c) => /\{\{\s*Item\./.test(c));
                  return (
                    <tr key={ri} className={repeated ? 'itam-row-repeat' : undefined} title={repeated ? t('templateEditor.repeatRow') : undefined}>
                      {r.map((c, ci) => {
                        const head = b.headerRow && ri === 0;
                        return <td key={ci} style={{ fontWeight: head || (b.boldFirstColumn && ci === 0) || b.bold ? 700 : 400, background: head ? '#ededed' : undefined, textAlign: head ? 'center' : undefined, whiteSpace: 'pre-wrap' }}><Rich text={c} /></td>;
                      })}
                    </tr>
                  );
                })}</tbody>
              </table>
            );
          }
          default: return null;
        }
      })}
    </div>
  );
}

/** Web editor of document templates: blocks (headings, paragraphs, tables, signatures) with placeholders; saved as a new DOCX version. */
export default function TemplateEditorPage() {
  const { id } = useParams<{ id: string }>();
  const isNew = !id || id === 'new';
  const [params] = useSearchParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const notify = useNotify();
  const { message } = App.useApp();
  const [model, setModel] = useState<Model>();
  const [dirty, setDirty] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [note, setNote] = useState('');
  const [search, setSearch] = useState('');
  const [meta] = Form.useForm();
  const docType = Form.useWatch('documentType', meta) as string | undefined;
  const focus = useRef<Focus>();

  const editor = useQuery<EditorDto>({
    queryKey: ['template-editor', id, params.get('versionId')], enabled: !isNew,
    queryFn: () => get(`/templates/${id}/editor`, { versionId: params.get('versionId') ?? undefined }),
  });
  const placeholders = useQuery<Placeholder[]>({
    queryKey: ['placeholders', isNew ? docType : editor.data?.documentType], enabled: isNew ? !!docType : !!editor.data,
    queryFn: () => get(`/templates/placeholders/${isNew ? docType : editor.data!.documentType}`),
  });
  const templates = useQuery<TplListItem[]>({ queryKey: ['templates-admin'], queryFn: () => get('/templates', { includeArchived: true }), enabled: isNew });

  useEffect(() => { if (editor.data && !model) setModel(editor.data.model); }, [editor.data, model]);
  useEffect(() => { if (isNew && !model) setModel(blankModel()); }, [isNew, model]);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const update = (fn: (blocks: Block[]) => Block[]) => { setModel((m) => (m ? { blocks: fn(m.blocks.map((b) => ({ ...b, rows: b.rows?.map((r) => [...r]) }))) } : m)); setDirty(true); };
  const patch = (i: number, p: Partial<Block>) => update((bs) => bs.map((b, bi) => (bi === i ? { ...b, ...p } : b)));
  const insert = (at: number, b: Block) => update((bs) => [...bs.slice(0, at), b, ...bs.slice(at)]);
  const move = (i: number, d: number) => update((bs) => { const j = i + d; if (j < 0 || j >= bs.length) return bs; [bs[i], bs[j]] = [bs[j], bs[i]]; return bs; });

  /** Inserts {{key}} at the cursor of the last focused field (or appends to the last paragraph). */
  const insertPlaceholder = (key: string) => {
    const token = `{{${key}}}`;
    const f = focus.current;
    if (!model) return;
    if (!f || !document.body.contains(f.el)) { message.info(t('templateEditor.focusField')); return; }
    const el = f.el;
    const value = el.value;
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    const next = value.slice(0, start) + token + value.slice(end);
    if (f.row === undefined) patch(f.block, { text: next });
    else update((bs) => bs.map((b, bi) => (bi === f.block ? { ...b, rows: b.rows!.map((r, ri) => (ri === f.row ? r.map((c, ci) => (ci === f.col ? next : c)) : r)) } : b)));
    setTimeout(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); }, 0);
  };
  const track = (block: number, row?: number, col?: number) => (e: React.FocusEvent<HTMLTextAreaElement | HTMLInputElement>) => { focus.current = { block, row, col, el: e.target }; };

  const save = useApiMutation(async () => {
    if (isNew) {
      const v = await meta.validateFields();
      return post<{ id: string }>('/templates/editor', { ...v, model });
    }
    return post<{ id: string }>(`/templates/${id}/editor`, { model, changeNote: note, activate: true });
  }, { invalidate: [['templates-admin'], ['templates'], ['template', id], ['template-editor']], success: t('templateEditor.saved'), onSuccess: (r) => {
    setDirty(false); setSaveOpen(false); setNote('');
    navigate(`/admin/templates/${isNew ? r.id : id}`);
  } });
  const preview = useApiMutation(async () => {
    const res = await api.post<Blob>('/templates/editor/preview', { model }, { responseType: 'blob' });
    const href = URL.createObjectURL(res.data);
    if (res.data.type === 'application/pdf') window.open(href, '_blank', 'noopener');
    else { const a = document.createElement('a'); a.href = href; a.download = 'preview.docx'; a.click(); }
    setTimeout(() => URL.revokeObjectURL(href), 60000);
  }, { success: false });

  const loadFrom = async (templateId: string) => {
    const dto = await get<EditorDto>(`/templates/${templateId}/editor`);
    setModel(dto.model); setDirty(true);
  };

  const phList = useMemo(() => (placeholders.data ?? editor.data?.availablePlaceholders ?? [])
    .filter((p) => !search || p.key.toLowerCase().includes(search.toLowerCase()) || p.description.toLowerCase().includes(search.toLowerCase())), [placeholders.data, editor.data, search]);

  if ((!isNew && editor.isLoading) || !model) return <Skeleton active />;
  const title = isNew ? t('templateEditor.newTitle') : `${t('templateEditor.title')}: ${editor.data?.name}`;

  const addMenu = (at: number) => ({ items: PRESETS.map((p) => ({ key: p.key, label: t(`templateEditor.preset.${p.key}`), onClick: () => insert(at, p.block()) })) });

  const blockCard = (b: Block, i: number) => {
    const toolbar = (
      <Space size={4}>
        <Tooltip title={t('templateEditor.up')}><Button size="small" type="text" icon={<ArrowUpOutlined />} disabled={i === 0} onClick={() => move(i, -1)} /></Tooltip>
        <Tooltip title={t('templateEditor.down')}><Button size="small" type="text" icon={<ArrowDownOutlined />} disabled={i === model.blocks.length - 1} onClick={() => move(i, 1)} /></Tooltip>
        <Tooltip title={t('templateEditor.duplicate')}><Button size="small" type="text" icon={<CopyOutlined />} onClick={() => insert(i + 1, structuredClone(b))} /></Tooltip>
        <Tooltip title={t('common.delete')}><Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => update((bs) => bs.filter((_, bi) => bi !== i))} /></Tooltip>
      </Space>
    );
    const textTools = (
      <Space wrap size={6} style={{ marginBottom: 8 }}>
        {b.type === 'paragraph' && <Button size="small" type={b.bold ? 'primary' : 'default'} icon={<BoldOutlined />} onClick={() => patch(i, { bold: !b.bold })} />}
        <Button size="small" type={b.italic ? 'primary' : 'default'} icon={<ItalicOutlined />} onClick={() => patch(i, { italic: !b.italic })} />
        <Button size="small" type={b.underline ? 'primary' : 'default'} icon={<UnderlineOutlined />} onClick={() => patch(i, { underline: !b.underline })} />
        <Segmented size="small" value={b.align ?? (b.type === 'heading' ? 'center' : 'left')} onChange={(v) => patch(i, { align: v as Align })}
          options={[{ value: 'left', icon: <AlignLeftOutlined /> }, { value: 'center', icon: <AlignCenterOutlined /> }, { value: 'right', icon: <AlignRightOutlined /> }, { value: 'both', icon: <MenuOutlined /> }]} />
        <InputNumber size="small" min={6} max={72} value={b.fontSize ?? (b.type === 'heading' ? 14 : 11)} onChange={(v) => patch(i, { fontSize: v ?? undefined })} addonAfter="pt" style={{ width: 100 }} />
      </Space>
    );
    let body: React.ReactNode = null;
    if (b.type === 'heading' || b.type === 'paragraph') {
      body = <>{textTools}<Input.TextArea autoSize={{ minRows: 1, maxRows: 12 }} value={b.text} onFocus={track(i)} onChange={(e) => patch(i, { text: e.target.value })}
        style={textStyle(b, b.type === 'heading' ? 14 : 11)} placeholder={t('templateEditor.textPlaceholder')} /></>;
    } else if (b.type === 'table') {
      const rows = b.rows ?? [];
      const cols = rows.reduce((n, r) => Math.max(n, r.length), 0);
      body = (
        <>
          <Space wrap style={{ marginBottom: 8 }}>
            <Checkbox checked={!!b.headerRow} onChange={(e) => patch(i, { headerRow: e.target.checked })}>{t('templateEditor.headerRow')}</Checkbox>
            <Checkbox checked={!!b.boldFirstColumn} onChange={(e) => patch(i, { boldFirstColumn: e.target.checked })}>{t('templateEditor.boldFirstColumn')}</Checkbox>
            <Checkbox checked={b.borders !== false} onChange={(e) => patch(i, { borders: e.target.checked })}>{t('templateEditor.borders')}</Checkbox>
            <InputNumber size="small" min={6} max={72} value={b.fontSize ?? 10} onChange={(v) => patch(i, { fontSize: v ?? undefined })} addonAfter="pt" style={{ width: 100 }} />
          </Space>
          <div style={{ overflowX: 'auto' }}>
            <table className="itam-edit-table">
              <thead><tr>
                {Array.from({ length: cols }, (_, c) => (
                  <th key={c}>
                    <Space size={2}>
                      <InputNumber size="small" min={1} max={100} placeholder="%" style={{ width: 64 }} value={b.columnWidths?.[c]}
                        title={t('templateEditor.columnWidth')}
                        onChange={(v) => { const w = b.columnWidths && b.columnWidths.length === cols ? [...b.columnWidths] : Array(cols).fill(Math.round(100 / cols)); w[c] = v ?? 1; patch(i, { columnWidths: w }); }} />
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} disabled={cols <= 1} title={t('templateEditor.removeColumn')}
                        onClick={() => patch(i, { rows: rows.map((r) => r.filter((_, ci) => ci !== c)), columnWidths: b.columnWidths?.filter((_, ci) => ci !== c) ?? null })} />
                    </Space>
                  </th>
                ))}
                <th />
              </tr></thead>
              <tbody>{rows.map((r, ri) => (
                <tr key={ri}>
                  {Array.from({ length: cols }, (_, c) => (
                    <td key={c}><Input.TextArea autoSize={{ minRows: 1, maxRows: 6 }} value={r[c] ?? ''} onFocus={track(i, ri, c)}
                      style={{ fontWeight: (b.headerRow && ri === 0) || (b.boldFirstColumn && c === 0) ? 600 : 400, minWidth: 110 }}
                      onChange={(e) => update((bs) => bs.map((x, bi) => (bi === i ? { ...x, rows: x.rows!.map((rr, rj) => (rj === ri ? Array.from({ length: cols }, (_, cc) => (cc === c ? e.target.value : rr[cc] ?? '')) : rr)) } : x)))} /></td>
                  ))}
                  <td><Button size="small" type="text" danger icon={<DeleteOutlined />} disabled={rows.length <= 1} title={t('templateEditor.removeRow')}
                    onClick={() => patch(i, { rows: rows.filter((_, rj) => rj !== ri) })} /></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <Space style={{ marginTop: 8 }}>
            <Button size="small" icon={<PlusOutlined />} onClick={() => patch(i, { rows: [...rows, Array(cols).fill('')] })}>{t('templateEditor.addRow')}</Button>
            <Button size="small" icon={<PlusOutlined />} disabled={cols >= 12} onClick={() => patch(i, { rows: rows.map((r) => [...r, '']), columnWidths: null })}>{t('templateEditor.addColumn')}</Button>
          </Space>
          {rows.some((r) => r.some((c) => /\{\{\s*Item\./.test(c))) && <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0', fontSize: 12 }}>{t('templateEditor.repeatRow')}</Typography.Paragraph>}
        </>
      );
    } else if (b.type === 'signatures') {
      const rows = b.rows ?? [];
      body = (
        <>
          {rows.map((r, ri) => (
            <Space key={ri} style={{ display: 'flex', marginBottom: 6 }} align="start">
              <Input value={r[0]} placeholder={t('templateEditor.signRole')} onFocus={track(i, ri, 0)} style={{ width: 220, fontWeight: 600 }}
                onChange={(e) => patch(i, { rows: rows.map((x, rj) => (rj === ri ? [e.target.value, x[1] ?? ''] : x)) })} />
              <span className="itam-muted">____________</span>
              <Input value={r[1]} placeholder={t('templateEditor.signName')} onFocus={track(i, ri, 1)} style={{ width: 260 }}
                onChange={(e) => patch(i, { rows: rows.map((x, rj) => (rj === ri ? [x[0] ?? '', e.target.value] : x)) })} />
              <Button size="small" type="text" danger icon={<DeleteOutlined />} disabled={rows.length <= 1} onClick={() => patch(i, { rows: rows.filter((_, rj) => rj !== ri) })} />
            </Space>
          ))}
          <Button size="small" icon={<PlusOutlined />} onClick={() => patch(i, { rows: [...rows, ['', '']] })}>{t('templateEditor.addSigner')}</Button>
        </>
      );
    }
    return (
      <Card key={i} size="small" className="itam-block" title={<Typography.Text type="secondary" style={{ fontSize: 12 }}>{t(`templateEditor.block.${b.type}`)}</Typography.Text>} extra={toolbar}
        styles={{ body: { display: body ? undefined : 'none' } }}>
        {body}
      </Card>
    );
  };

  return (
    <>
      <PageHeader title={title} crumbs={[{ title: t('menu.templates'), to: '/admin/templates' }, ...(isNew ? [] : [{ title: editor.data!.name, to: `/admin/templates/${id}` }]), { title: t('templateEditor.crumb') }]}
        extra={<>
          <Button icon={<EyeOutlined />} loading={preview.isPending} onClick={() => preview.mutate(undefined)}>{t('templateEditor.previewPdf')}</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={save.isPending} onClick={() => (isNew ? save.mutate(undefined) : setSaveOpen(true))}>
            {isNew ? t('templateEditor.create') : t('templateEditor.saveVersion')}
          </Button>
        </>} />
      {!isNew && editor.data?.fromDocx && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message={t('templateEditor.fromDocx', { v: editor.data.versionNumber })} />}
      {isNew && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Form form={meta} layout="vertical" initialValues={{ documentType: 'EquipmentIssue', isDefault: false }}>
            <Row gutter={12}>
              <Col xs={24} md={8}><Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}><Input /></Form.Item></Col>
              <Col xs={24} md={6}><Form.Item name="documentType" label={t('documents.type')} rules={[{ required: true }]}><EnumSelect group="documentType" values={DOCUMENT_TYPES} allowClear={false} /></Form.Item></Col>
              <Col xs={24} md={4}><Form.Item name="code" label={t('common.code')}><Input /></Form.Item></Col>
              <Col xs={24} md={6}>
                <Form.Item label={t('templateEditor.startFrom')}>
                  <Select allowClear placeholder={t('templateEditor.startBlank')} onChange={(v) => (v ? loadFrom(v).catch(notify.error) : (setModel(blankModel()), setDirty(true)))}
                    options={(templates.data ?? []).filter((x) => !x.isArchived && (!docType || x.documentType === docType)).map((x) => ({ value: x.id, label: x.name }))} />
                </Form.Item>
              </Col>
              <Col span={24}><Form.Item name="isDefault" valuePropName="checked" style={{ marginBottom: 0 }}><Checkbox>{t('templates.makeDefault')}</Checkbox></Form.Item></Col>
            </Row>
          </Form>
        </Card>
      )}
      <Row gutter={16}>
        <Col xs={24} xl={14}>
          {model.blocks.length === 0 && <Card><Empty description={t('templateEditor.emptyModel')} /></Card>}
          {model.blocks.map((b, i) => (
            <Fragment key={i}>
              <div className="itam-insert"><Dropdown menu={addMenu(i)} trigger={['click']}><Button size="small" type="dashed" icon={<PlusOutlined />}>{t('templateEditor.insert')}</Button></Dropdown></div>
              {blockCard(b, i)}
            </Fragment>
          ))}
          <div className="itam-insert"><Dropdown menu={addMenu(model.blocks.length)} trigger={['click']}><Button type="dashed" icon={<PlusOutlined />} block>{t('templateEditor.addBlock')}</Button></Dropdown></div>
        </Col>
        <Col xs={24} xl={10}>
          <div style={{ position: 'sticky', top: 72 }}>
            <Card size="small">
              <Tabs items={[
                {
                  key: 'ph', label: t('templateEditor.placeholdersTab'), children: (
                    <>
                      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>{t('templateEditor.placeholdersHint')}</Typography.Paragraph>
                      <Input.Search allowClear placeholder={t('common.search')} value={search} onChange={(e) => setSearch(e.target.value)} style={{ marginBottom: 8 }} />
                      <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
                        {phList.filter((p) => !p.key.includes('<')).map((p) => (
                          <div key={p.key} className="itam-ph-item" onMouseDown={(e) => e.preventDefault()} onClick={() => insertPlaceholder(p.key)}>
                            <Typography.Text code className="itam-mono">{`{{${p.key}}}`}</Typography.Text>
                            <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>{p.description}</Typography.Text>
                          </div>
                        ))}
                      </div>
                    </>
                  ),
                },
                { key: 'preview', label: t('templateEditor.previewTab'), children: <div style={{ maxHeight: '75vh', overflowY: 'auto' }}><Preview model={model} /></div> },
              ]} />
            </Card>
          </div>
        </Col>
      </Row>
      <Modal open={saveOpen} title={t('templateEditor.saveVersion')} onCancel={() => setSaveOpen(false)} onOk={() => save.mutate(undefined)} confirmLoading={save.isPending}>
        <Typography.Paragraph type="secondary">{t('templateEditor.saveHint')}</Typography.Paragraph>
        <Input.TextArea rows={2} placeholder={t('templates.changeNote')} value={note} onChange={(e) => setNote(e.target.value)} />
      </Modal>
    </>
  );
}
