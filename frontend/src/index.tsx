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

const App = () => (
  <BrowserRouter>
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
      </Routes>
    </Layout>
  </BrowserRouter>
);

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
