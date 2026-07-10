/** Demo data source fixtures from server/app/seed.py DATA_SOURCES */
import type { DataSource } from '../../api/types';

export const DEMO_SOURCES: DataSource[] = [
  { id: 'src-code', type: 'code', name: '源代码', connector_kind: 'CodeExplorer', conn: 'GitHub · company/backend', status: 'connected', progress: null },
  { id: 'src-db', type: 'db', name: '数据库', connector_kind: 'DatabaseExplorer', conn: 'PostgreSQL · prod-db', status: 'connected', progress: null },
  { id: 'src-api', type: 'api', name: 'API', connector_kind: 'APIExplorer', conn: 'OpenAPI · /api/v1/docs', status: 'connected', progress: null },
  { id: 'src-admin', type: 'admin', name: '管理后台', connector_kind: 'AdminPanelExplorer', conn: 'admin.company.com', status: 'running', progress: 45 },
  { id: 'src-doc', type: 'doc', name: '文档', connector_kind: 'DocExplorer', conn: 'Confluence · Engineering', status: 'connected', progress: null },
];
