import React, { useState, useEffect } from 'react';

const frequencyOptions = [
  { value: 'days', label: 'Tage' },
  { value: 'minutes', label: 'Minuten' },
];

const Settings: React.FC = () => {
  // Email grabber frequency
  const [frequencyType, setFrequencyType] = useState<'days' | 'minutes'>('days');
  const [frequencyValue, setFrequencyValue] = useState<number | ''>('');

  // Email types
  const [emailTypes, setEmailTypes] = useState<{ topic: string; description: string }[]>([]);
  const [newEmailType, setNewEmailType] = useState({ topic: '', description: '' });

  // Key features
  const [keyFeatures, setKeyFeatures] = useState<string[]>([]);
  const [newKeyFeature, setNewKeyFeature] = useState('');

  // Workflows (Integrated from WorkflowBuilder)
  const [workflowName, setWorkflowName] = useState<string>('');
  const [model, setModel] = useState<string>('gpt-4'); // Default model
  const [maxTokens, setMaxTokens] = useState<number | string>(1024);
  const [description, setDescription] = useState<string>('');
  const [selectedSteps, setSelectedSteps] = useState<string[]>([]);
  const [savingWorkflow, setSavingWorkflow] = useState<boolean>(false); // Renamed to avoid conflict
  const [savedWorkflows, setSavedWorkflows] = useState<any[]>([]); // Renamed to avoid conflict

  // State for editing workflow
  const [editingWorkflowId, setEditingWorkflowId] = useState<string | null>(null); // New state for tracking the workflow being edited

  // State for the new workflow form fields (moved from WorkflowBuilder's newWorkflow state)
  const [newWorkflowForm, setNewWorkflowForm] = useState({
    type: '',
    emailBody: '',
    emailTarget: '',
    model: '', // This will be set from the main 'model' state
    maxTokens: '', // This will be set from the main 'maxTokens' state
    subject: '',
    keyFeature: '',
    selectedTopic: '', // Add selectedTopic to state
  });

  const [loadingSettings, setLoadingSettings] = useState<boolean>(true); // New state for loading settings
  const [savingSettings, setSavingSettings] = useState<boolean>(false); // New state for saving settings
  const [settingsError, setSettingsError] = useState<string | null>(null); // New state for settings errors

  const availableSteps = [
    { id: 'compliance_agent', label: 'Compliance Agent' },
    { id: 'human_verification', label: 'Human Verification' },
    { id: 'document_processing', label: 'Document Processing' },
    { id: 'send_email', label: 'Send Email' },
  ];

  // Fetch settings on component mount
  useEffect(() => {
    const fetchSettings = async () => {
      setLoadingSettings(true);
      setSettingsError(null);
      try {
        const response = await fetch('/api/settings');
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`Failed to fetch settings: ${response.status} ${response.statusText} - ${errorText}`);
        }
        const data = await response.json();
        setFrequencyType(data.email_grabber_frequency_type || 'days');
        setFrequencyValue(data.email_grabber_frequency_value || '');
        setEmailTypes(data.email_types || []);
        setKeyFeatures(data.key_features.map((kf: { name: string }) => kf.name) || []); // Map key features to string array
      } catch (err: any) {
        setSettingsError(err.message);
        console.error("Fetch settings error:", err);
      } finally {
        setLoadingSettings(false);
      }
    };
    fetchSettings();
  }, []); // Empty dependency array means this runs once on mount

  // Handlers for Email Grabber Frequency
  const handleFrequencyChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setFrequencyType(e.target.value as 'days' | 'minutes');
  };
  const handleFrequencyValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFrequencyValue(e.target.value === '' ? '' : Number(e.target.value));
  };

  // Email Types
  const addEmailType = () => {
    if (newEmailType.topic && newEmailType.description) {
      setEmailTypes([...emailTypes, newEmailType]);
      setNewEmailType({ topic: '', description: '' });
    }
  };
  const removeEmailType = (idx: number) => {
    setEmailTypes(emailTypes.filter((_, i) => i !== idx));
  };

  // Key Features
  const addKeyFeature = () => {
    if (newKeyFeature && !keyFeatures.includes(newKeyFeature)) {
      setKeyFeatures([...keyFeatures, newKeyFeature]);
      setNewKeyFeature('');
    }
  };
  const removeKeyFeature = (idx: number) => {
    setKeyFeatures(keyFeatures.filter((_, i) => i !== idx));
  };

  // Handler for saving all settings
  const handleSaveSettings = async () => {
    setSavingSettings(true);
    setSettingsError(null);
    const settingsPayload = {
      email_grabber_frequency_type: frequencyType,
      email_grabber_frequency_value: Number(frequencyValue),
      email_types: emailTypes,
      key_features: keyFeatures.map(kf => ({ name: kf })), // Map string array back to object array
    };

    try {
      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settingsPayload),
      });

      if (response.ok) {
        alert('Einstellungen erfolgreich gespeichert!');
      } else {
        const errorData = await response.json();
        throw new Error(`Fehler beim Speichern der Einstellungen: ${errorData.detail || response.statusText}`);
      }
    } catch (err: any) {
      setSettingsError(err.message);
      console.error("Save settings error:", err);
      alert(`Fehler beim Speichern der Einstellungen: ${err.message}`);
    } finally {
      setSavingSettings(false);
    }
  };

  // Workflow Handlers (Integrated from WorkflowBuilder)
  const handleStepChange = (stepId: string) => {
    setSelectedSteps(prevSteps =>
      prevSteps.includes(stepId)
        ? prevSteps.filter(s => s !== stepId)
        : [...prevSteps, stepId]
    );
  };

  const handleWorkflowSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSavingWorkflow(true);

    const workflowConfigData: any = {
      model: model, // Use main model state
      max_tokens: maxTokens === '' ? undefined : parseInt(maxTokens as string, 10), // Use main maxTokens state
      steps: selectedSteps,
      initial_status: 'pending', // Default, can be made configurable
      frequency_type: frequencyType, // Include frequency in workflow config
      frequency_value: frequencyValue, // Include frequency in workflow config
      // Include email action fields in workflow_config if needed by backend workflow execution
      to: newWorkflowForm.emailTarget,
      subject: newWorkflowForm.subject,
      body: newWorkflowForm.emailBody,
      key_feature: newWorkflowForm.keyFeature, // Include key feature
      selected_topic: newWorkflowForm.selectedTopic, // Include selected topic
    };

    const payload: any = {
      workflow_name: workflowName,
      trigger_type: 'cron', // Always cron for now
      description: description,
      workflow_config: workflowConfigData,
      type: 'cron', // Aligning SchedulerTask.type with the triggerType for now
      status: 'active', // Status of the scheduler task itself
    };

    // Clean up undefined optional fields before sending
    Object.keys(payload).forEach(key => {
        if (payload[key] === undefined || payload[key] === null || payload[key] === '') {
             delete payload[key];
        }
    });
    if (payload.workflow_config) {
        Object.keys(payload.workflow_config).forEach(key => {
            if (payload.workflow_config[key] === undefined || payload.workflow_config[key] === null || payload.workflow_config[key] === '') {
                 delete payload.workflow_config[key];
            }
        });
    }

    const method = editingWorkflowId ? 'PUT' : 'POST';
    const url = editingWorkflowId ? `/api/scheduler/task/${editingWorkflowId}` : '/api/scheduler/task';

    try {
      const response = await fetch(url, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const result = await response.json();
        alert(`Workflow ${editingWorkflowId ? 'updated' : 'saved'} successfully!`);
        console.log(`Workflow ${editingWorkflowId ? 'updated' : 'saved'}:`, result);
        // Refresh saved workflows list
        fetchWorkflows();
        // Reset workflow form fields and editing state
        setWorkflowName('');
        setDescription('');
        setSelectedSteps([]);
        setModel('gpt-4'); // Reset main model state
        setMaxTokens(1024); // Reset main maxTokens state
        setNewWorkflowForm({ // Reset new workflow form state
          type: '',
          emailBody: '',
          emailTarget: '',
          model: '',
          maxTokens: '',
          subject: '',
          keyFeature: '',
          selectedTopic: '', // Reset selectedTopic
        });
        setEditingWorkflowId(null); // Clear editing state

      } else {
        const errorData = await response.json();
        alert(`Error ${editingWorkflowId ? 'updating' : 'saving'} workflow: ${errorData.detail || response.statusText}`);
        console.error(`Error ${editingWorkflowId ? 'updating' : 'saving'} workflow:`, errorData);
      }
    } catch (error) {
      alert(`Error ${editingWorkflowId ? 'updating' : 'saving'} workflow: ${error}`);
      console.error('Network or other error:', error);
    } finally {
      setSavingWorkflow(false);
    }
  };

  const handleDeleteWorkflow = async (id: string) => {
    if (!window.confirm('Workflow wirklich löschen?')) return;
    try {
      const response = await fetch(`/api/scheduler/task/${id}`, { method: 'DELETE' });
      if (response.ok) {
        alert('Workflow gelöscht!');
        fetchWorkflows(); // Refresh list
      } else {
         const errorData = await response.json();
         alert(`Error deleting workflow: ${errorData.detail || response.statusText}`);
         console.error('Error deleting workflow:', errorData);
      }
    } catch (error) {
       alert(`Error deleting workflow: ${error}`);
       console.error('Network or other error:', error);
    }
  };

  // New handler for editing a workflow
  const handleEditWorkflow = (workflow: any) => {
    setEditingWorkflowId(workflow.id);
    setWorkflowName(workflow.workflow_name);
    setDescription(workflow.description);
    setSelectedSteps(workflow.workflow_config?.steps || []);
    setModel(workflow.workflow_config?.model || 'gpt-4');
    setMaxTokens(workflow.workflow_config?.max_tokens || 1024);
    setNewWorkflowForm({
      type: '', // Assuming type is not directly editable via this form
      emailBody: workflow.workflow_config?.body || '',
      emailTarget: workflow.workflow_config?.to || '',
      model: '', // This will be overwritten by setModel
      maxTokens: '', // This will be overwritten by setMaxTokens
      subject: workflow.workflow_config?.subject || '',
      keyFeature: workflow.workflow_config?.key_feature || '',
      selectedTopic: workflow.workflow_config?.selected_topic || '',
    });
  };

  // Handler to cancel editing
  const handleCancelEdit = () => {
    setEditingWorkflowId(null);
    setWorkflowName('');
    setDescription('');
    setSelectedSteps([]);
    setModel('gpt-4');
    setMaxTokens(1024);
    setNewWorkflowForm({
      type: '',
      emailBody: '',
      emailTarget: '',
      model: '',
      maxTokens: '',
      subject: '',
      keyFeature: '',
      selectedTopic: '',
    });
  };

  // Fetch saved workflows on component mount and after saving/deleting
  const fetchWorkflows = async () => {
    try {
      const res = await fetch('/api/scheduler/tasks');
      if (res.ok) {
        setSavedWorkflows(await res.json());
      }
    } catch (error) {
      console.error('Error fetching workflows:', error);
    }
  };

  useEffect(() => {
    fetchWorkflows();
  }, [savingWorkflow]); // Depend on savingWorkflow to refetch after save/delete

  if (loadingSettings) return <div className="p-6 text-center">Loading settings...</div>;
  if (settingsError) return <div className="p-6 text-center text-red-500">Error loading settings: {settingsError}</div>;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-8">
      {/* Email Grabber Frequency */}
      <section>
        <h2 className="text-xl font-bold mb-2">Email Grabber Frequenz</h2>
        <div className="flex gap-2 items-center">
          <select value={frequencyType} onChange={handleFrequencyChange} className="border rounded px-2 py-1">
            {frequencyOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <input
            type="number"
            min={1}
            value={frequencyValue}
            onChange={handleFrequencyValueChange}
            className="border rounded px-2 py-1 w-24"
            placeholder="Anzahl"
            required
          />
          <span>{frequencyType === 'days' ? 'Tag(e)' : 'Minute(n)'}</span>
        </div>
      </section>

      {/* Emailtypen */}
      <section>
        <h2 className="text-xl font-bold mb-2">Emailtypen</h2>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            placeholder="Topic"
            value={newEmailType.topic}
            onChange={e => setNewEmailType({ ...newEmailType, topic: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <input
            type="text"
            placeholder="Beschreibung"
            value={newEmailType.description}
            onChange={e => setNewEmailType({ ...newEmailType, description: e.target.value })}
            className="border rounded px-2 py-1"
          />
          <button onClick={addEmailType} className="bg-blue-500 text-white px-3 py-1 rounded">Hinzufügen</button>
        </div>
        <ul className="space-y-1">
          {emailTypes.map((et, idx) => (
            <li key={idx} className="flex gap-2 items-center">
              <span className="font-semibold">{et.topic}</span>
              <span className="text-gray-500">{et.description}</span>
              <button onClick={() => removeEmailType(idx)} className="text-red-500 ml-2">Entfernen</button>
            </li>
          ))}
        </ul>
      </section>

      {/* Key Features */}
      <section>
        <h2 className="text-xl font-bold mb-2">Key Features</h2>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            placeholder="z.B. Name, Adresse, ..."
            value={newKeyFeature}
            onChange={e => setNewKeyFeature(e.target.value)}
            className="border rounded px-2 py-1"
          />
          <button onClick={addKeyFeature} className="bg-blue-500 text-white px-3 py-1 rounded">Hinzufügen</button>
        </div>
        <ul className="space-y-1">
          {keyFeatures.map((kf, idx) => (
            <li key={idx} className="flex gap-2 items-center">
              <span>{kf}</span>
              <button onClick={() => removeKeyFeature(idx)} className="text-red-500 ml-2">Entfernen</button>
            </li>
          ))}
        </ul>
      </section>

      {/* Save Settings Button */}
      <div className="pt-4">
        <button
          onClick={handleSaveSettings}
          disabled={savingSettings}
          className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50"
        >
          {savingSettings ? 'Speichern...' : 'Einstellungen speichern'}
        </button>
      </div>

      {/* Workflows (Integrated from WorkflowBuilder) */}
      <section>
        <h2 className="text-xl font-bold mb-2">Workflows</h2>
        <form onSubmit={handleWorkflowSubmit} className="space-y-4 mb-4 p-4 border rounded-md bg-gray-50">
          {/* Workflow Name */}
          <div>
            <label htmlFor="workflowName" className="block text-sm font-medium text-gray-700 mb-1">
              Workflow Name
            </label>
            <input
              type="text"
              id="workflowName"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="e.g., Daily Email Summary"
              required
            />
          </div>

          {/* Description */}
          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
              placeholder="Describe what this workflow does"
            />
          </div>

          {/* Workflow Steps Selection */}
          <fieldset className="border p-4 rounded-md">
            <legend className="text-lg font-medium text-gray-700 px-1">Workflow Steps</legend>
            <div className="space-y-2 mt-2">
              {availableSteps.map(step => (
                <div key={step.id} className="flex items-center">
                  <input
                    id={`step-${step.id}`}
                    name={`step-${step.id}`}
                    type="checkbox"
                    checked={selectedSteps.includes(step.id)}
                    onChange={() => handleStepChange(step.id)}
                    className="h-4 w-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                  />
                  <label htmlFor={`step-${step.id}`} className="ml-2 block text-sm text-gray-900">
                    {step.label}
                  </label>
                </div>
              ))}
            </div>
          </fieldset>

          {/* Model Configuration - General for workflows that might use an LLM */}
          <fieldset className="border p-4 rounded-md">
            <legend className="text-lg font-medium text-gray-700 px-1">LLM Configuration (Optional)</legend>
            <div className="space-y-4 mt-2">
              <div>
                <label htmlFor="model" className="block text-sm font-medium text-gray-700 mb-1">
                  Model Name
                </label>
                <input
                  type="text"
                  id="model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="e.g., gpt-4, gemini-pro"
                />
              </div>
              <div>
                <label htmlFor="maxTokens" className="block text-sm font-medium text-gray-700 mb-1">
                  Max Tokens
                </label>
                <input
                  type="number"
                  id="maxTokens"
                  value={maxTokens}
                  onChange={(e) => setMaxTokens(e.target.value === '' ? '' : Number(e.target.value))}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="e.g., 1024"
                />
              </div>
            </div>
          </fieldset>

          {/* Email Action Specific Fields - These could be part of a specific "action step" in a more complex builder */}
          <fieldset className="border p-4 rounded-md">
            <legend className="text-lg font-medium text-gray-700 px-1">Email Action Configuration (If Applicable)</legend>
            <div className="space-y-4 mt-2">
              {/* Selected Topic Dropdown */}
              <div>
                <label htmlFor="selectedTopic" className="block text-sm font-medium text-gray-700 mb-1">
                  Select Topic
                </label>
                <select
                  id="selectedTopic"
                  value={newWorkflowForm.selectedTopic}
                  onChange={(e) => setNewWorkflowForm({ ...newWorkflowForm, selectedTopic: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                >
                  <option value="">-- Select a Topic --</option>
                  {emailTypes.map((et, idx) => (
                    <option key={idx} value={et.topic}>{et.topic}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="toEmail" className="block text-sm font-medium text-gray-700 mb-1">
                  Recipient Email (To)
                </label>
                <input
                  type="email"
                  id="toEmail"
                  value={newWorkflowForm.emailTarget} // Use newWorkflowForm state
                  onChange={(e) => setNewWorkflowForm({ ...newWorkflowForm, emailTarget: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="recipient@example.com"
                />
              </div>
              <div>
                <label htmlFor="emailSubject" className="block text-sm font-medium text-gray-700 mb-1">
                  Email Subject
                </label>
                <input
                  type="text"
                  id="emailSubject"
                  value={newWorkflowForm.subject} // Use newWorkflowForm state
                  onChange={(e) => setNewWorkflowForm({ ...newWorkflowForm, subject: e.target.value })}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="Your Email Subject"
                />
              </div>
              <div>
                <label htmlFor="emailBody" className="block text-sm font-medium text-gray-700 mb-1">
                  Email Body
                </label>
                <textarea
                  id="emailBody"
                  value={newWorkflowForm.emailBody} // Use newWorkflowForm state
                  onChange={(e) => setNewWorkflowForm({ ...newWorkflowForm, emailBody: e.target.value })}
                  rows={4}
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                  placeholder="Compose your email body here..."
                />
              </div>
            </div>
          </fieldset>

          <div className="pt-2">
            <button
              type="submit"
              disabled={savingWorkflow}
              className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
            >
              {savingWorkflow ? (editingWorkflowId ? 'Updating...' : 'Saving...') : (editingWorkflowId ? 'Update Workflow' : 'Save Workflow')}
            </button>
            {editingWorkflowId && (
              <button
                type="button"
                onClick={handleCancelEdit}
                className="mt-2 w-full flex justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                Cancel Edit
              </button>
            )}
          </div>
        </form>

        {/* Saved Workflows List */}
        <div className="mt-8">
          <h2 className="text-xl font-bold mb-2">Gespeicherte Workflows</h2>
          <div className="max-h-60 overflow-y-auto border rounded-md p-2">
            <ul>
              {savedWorkflows.map(wf => (
                <li key={wf.id} className="flex items-center gap-2 border-b py-2">
                  <span className="flex-1">{wf.workflow_name} ({wf.workflow_config?.frequency_value} {wf.workflow_config?.frequency_type}) - Topic: {wf.workflow_config?.selected_topic}</span>
                  {/* Add Edit Button */}
                  <button onClick={() => handleEditWorkflow(wf)} className="bg-yellow-500 text-white px-2 py-1 rounded text-xs">Bearbeiten</button>
                  <button onClick={() => handleDeleteWorkflow(wf.id)} className="bg-red-500 text-white px-2 py-1 rounded text-xs">Löschen</button>
                </li>
              ))}
              {savedWorkflows.length === 0 && <li className="text-gray-500">Keine Workflows gespeichert.</li>}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Settings;
