import React, { useState } from 'react';

const WorkflowBuilder: React.FC = () => {
  const [workflowName, setWorkflowName] = useState<string>('');
  const [triggerType, setTriggerType] = useState<string>('email_receive'); // Default trigger type
  const [model, setModel] = useState<string>('gpt-4'); // Default model
  const [maxTokens, setMaxTokens] = useState<number | string>(1024);
  const [description, setDescription] = useState<string>('');

  // Cron specific fields
  const [interval, setInterval] = useState<number | string>(''); // Interval in seconds

  // Email action specific fields
  const [toEmail, setToEmail] = useState<string>('');
  const [emailSubject, setEmailSubject] = useState<string>('');
  const [emailBody, setEmailBody] = useState<string>('');

  // State for workflow steps
  const [selectedSteps, setSelectedSteps] = useState<string[]>([]);
  const [saving, setSaving] = useState<boolean>(false);

  const availableSteps = [
    { id: 'compliance_agent', label: 'Compliance Agent' },
    { id: 'human_verification', label: 'Human Verification' },
    { id: 'document_processing', label: 'Document Processing' },
    { id: 'send_email', label: 'Send Email' },
  ];

  const handleStepChange = (stepId: string) => {
    setSelectedSteps(prevSteps =>
      prevSteps.includes(stepId)
        ? prevSteps.filter(s => s !== stepId)
        : [...prevSteps, stepId]
    );
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);

    const workflowConfigData: any = {
      model: model,
      max_tokens: maxTokens === '' ? undefined : parseInt(maxTokens as string, 10),
      steps: selectedSteps,
      initial_status: 'pending', // Default, can be made configurable
    };

    const payload: any = {
      workflow_name: workflowName,
      trigger_type: triggerType,
      description: description,
      workflow_config: workflowConfigData,
      type: triggerType, // Aligning SchedulerTask.type with the triggerType for now
      status: 'active', // Status of the scheduler task itself
    };

    if (triggerType === 'cron') {
      payload.interval_seconds = interval === '' ? undefined : parseInt(interval as string, 10);
      // payload.date_val = null; // Or add UI for this if specific start date/time needed
    }

    // Include email fields if "Send Email" step is selected or if they are filled (general purpose)
    // For this iteration, we'll include them if the "Send Email" step is selected,
    // or if any email field has a value (could be a general purpose workflow that sends an email)
    if (selectedSteps.includes('send_email') || toEmail || emailSubject || emailBody) {
      payload.to_email = toEmail;
      payload.subject = emailSubject;
      payload.body = emailBody;
    }

    // Clean up undefined optional fields before sending
    Object.keys(payload).forEach(key => {
        if (payload[key] === undefined || payload[key] === null || payload[key] === '') {
            // For optional fields, backend might expect them to be absent if not set, rather than null/empty.
            // However, for numbers like interval_seconds, 0 might be valid.
            // Adjust this logic based on backend expectations. For now, removing undefined/null/empty strings.
            if (key !== 'interval_seconds' || payload[key] === '') { // Keep interval_seconds if it's 0
                 delete payload[key];
            }
        }
    });
    if (payload.workflow_config) {
        Object.keys(payload.workflow_config).forEach(key => {
            if (payload.workflow_config[key] === undefined || payload.workflow_config[key] === null || payload.workflow_config[key] === '') {
                 delete payload.workflow_config[key];
            }
        });
    }


    try {
      const response = await fetch('/api/scheduler/task', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const result = await response.json();
        alert('Workflow saved successfully!');
        console.log('Workflow saved:', result);
        // Optionally reset form here
        // setWorkflowName('');
        // setTriggerType('email_receive');
        // ... reset other states
        // setSelectedSteps([]);
      } else {
        const errorData = await response.json();
        alert(`Error saving workflow: ${errorData.detail || response.statusText}`);
        console.error('Error saving workflow:', errorData);
      }
    } catch (error) {
      alert(`Error saving workflow: ${error}`);
      console.error('Network or other error:', error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="container mx-auto p-4 max-w-3xl">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-gray-800">Workflow Builder</h1>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white p-6 shadow-lg rounded-lg">
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
            className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
            placeholder="e.g., Daily Email Summary"
            required
          />
        </div>

        {/* Trigger Type Selection */}
        <div>
          <label htmlFor="triggerType" className="block text-sm font-medium text-gray-700 mb-1">
            Trigger Type
          </label>
          <select
            id="triggerType"
            value={triggerType}
            onChange={(e) => setTriggerType(e.target.value)}
            className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md"
          >
            <option value="email_receive">Email Receive</option>
            <option value="cron">Cron Job</option>
            {/* Add other trigger types as needed, e.g., 'manual', 'agent_event' */}
          </select>
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
            className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
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
                className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
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
                className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                placeholder="e.g., 1024"
              />
            </div>
          </div>
        </fieldset>

        {/* Cron Specific Fields - Conditional */}
        {triggerType === 'cron' && (
          <fieldset className="border p-4 rounded-md">
            <legend className="text-lg font-medium text-gray-700 px-1">Cron Configuration</legend>
            <div className="mt-2">
              <label htmlFor="interval" className="block text-sm font-medium text-gray-700 mb-1">
                Interval (seconds)
              </label>
              <input
                type="number"
                id="interval"
                value={interval}
                onChange={(e) => setInterval(e.target.value === '' ? '' : Number(e.target.value))}
                className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                placeholder="e.g., 3600 for hourly"
              />
              {/* Optional: Add date/time input for specific cron jobs if needed later */}
            </div>
          </fieldset>
        )}

        {/* Email Action Specific Fields - These could be part of a specific "action step" in a more complex builder */}
        {/* For now, let's assume they are configurable for workflows that might send an email. */}
        <fieldset className="border p-4 rounded-md">
          <legend className="text-lg font-medium text-gray-700 px-1">Email Action Configuration (If Applicable)</legend>
          <div className="space-y-4 mt-2">
            <div>
              <label htmlFor="toEmail" className="block text-sm font-medium text-gray-700 mb-1">
                Recipient Email (To)
              </label>
              <input
                type="email"
                id="toEmail"
                value={toEmail}
                onChange={(e) => setToEmail(e.target.value)}
                className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
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
                value={emailSubject}
                onChange={(e) => setEmailSubject(e.target.value)}
                className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                placeholder="Your Email Subject"
              />
            </div>
            <div>
              <label htmlFor="emailBody" className="block text-sm font-medium text-gray-700 mb-1">
                Email Body
              </label>
              <textarea
                id="emailBody"
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
                rows={4}
                className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm"
                placeholder="Compose your email body here..."
              />
            </div>
          </div>
        </fieldset>

        <div className="pt-2">
          <button
            type="submit"
            disabled={saving}
            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Workflow'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default WorkflowBuilder;
