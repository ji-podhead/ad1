import React from 'react';
import ReactDOM from 'react-dom/client';
// import './index.css'; // Uncomment if you add Tailwind/global styles

import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Inbox from './pages/Inbox';
import Documents from './pages/Documents';
import Validation from './pages/Validation';
import Audit from './pages/Audit';
import AgentChat from './pages/AgentChat';
import Tasks from './pages/Tasks';
import Layout from './components/Layout';
import Landing from './pages/Landing';
import IPAMPage from './pages/IPAM';
import About from './pages/About';
import UserManagementPage from './pages/UserManagementPage'; // Import UserManagementPage
import WorkflowBuilder from './pages/WorkflowBuilder'; // Import WorkflowBuilder
import { AuthProvider } from './contexts/AuthContext';

const App = () => (
  <BrowserRouter>
    <AuthProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Landing />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/validation" element={<Validation />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/chat" element={<AgentChat />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/ipam" element={<IPAMPage />} />
        <Route path="/about" element={<About />} />
        <Route path="/user-management" element={<UserManagementPage />} /> {/* Add UserManagementPage route */}
        <Route path="/workflow-builder" element={<WorkflowBuilder />} /> {/* Add WorkflowBuilder route */}
        </Routes>
      </Layout>
    </AuthProvider>
  </BrowserRouter>
);

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
