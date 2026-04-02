import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { OverviewPage } from '@/pages/OverviewPage';
import { MemoryExplorerPage } from '@/pages/MemoryExplorerPage';
import { KnowledgeGraphPage } from '@/pages/KnowledgeGraphPage';
import { AuditLogPage } from '@/pages/AuditLogPage';
import { SettingsPage } from '@/pages/SettingsPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="memories" element={<MemoryExplorerPage />} />
          <Route path="graph" element={<KnowledgeGraphPage />} />
          <Route path="audit" element={<AuditLogPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
