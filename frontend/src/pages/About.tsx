// About.tsx
// Renders the project README as HTML using react-markdown
import React, { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';

const About: React.FC = () => {
  const [markdown, setMarkdown] = useState('');

  useEffect(() => {
    fetch('/README.md')
      .then(res => res.text())
      .then(setMarkdown);
  }, []);

  return (
    <div className="prose max-w-3xl mx-auto p-6 bg-white rounded shadow">
      <h1 className="text-3xl font-bold mb-4">About ad1</h1>
      <ReactMarkdown>{markdown}</ReactMarkdown>
    </div>
  );
};

export default About;
