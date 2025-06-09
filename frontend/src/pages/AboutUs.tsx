import React from 'react';

const AboutUs: React.FC = () => {
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">About ad1</h1>

      <p className="mb-4">
        ad1 is a secure, modular platform for automated email and document processing, designed to meet strict Swiss and EU compliance requirements.
        It leverages intelligent agents, a persistent PostgreSQL database, audit trails, and a WebSocket-based chat for workflow orchestration.
      </p>

      <h2 className="text-2xl font-bold mb-4">Our Story</h2>
      <p className="mb-4">
        The project was originally initiated by Robert Schröder with the goal of simplifying orchestration processes for Swiss authorities.
        This led to the development of the multi-agent briefing concept, documented in the `briefing multiagent.md` file.
      </p>
      <p className="mb-4">
        The core team, Leonardo J. (ji-podhead), Yousif M., and Chrys Fé Marty Niongolo, met and connected over a hackathon organized by kxsb.
        This collaboration has been instrumental in shaping ad1 into the platform it is today.
      </p>

      <h2 className="text-2xl font-bold mb-4">The Team</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="bg-gray-100 p-4 rounded-lg">
          <h3 className="text-xl font-semibold">Leonardo J. (ji-podhead)</h3>
          <p className="text-gray-600">Project Owner</p>
          <p className="mt-2"><a href="https://www.linkedin.com/in/leonardo-j-09b358275/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">LinkedIn</a></p>
           {/* Add photo if link is provided later */}
        </div>
        <div className="bg-gray-100 p-4 rounded-lg">
          <h3 className="text-xl font-semibold">Yousif M.</h3>
          <p className="text-gray-600">Collaborator</p>
           <p className="text-gray-600">yousif@orchestra-nexus.com</p>
          <p className="mt-2"><a href="https://www.linkedin.com/in/yousifm/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">LinkedIn</a></p>
           {/* Add photo if link is provided later */}
        </div>
        <div className="bg-gray-100 p-4 rounded-lg">
          <h3 className="text-xl font-semibold">Chrys Fé Marty Niongolo</h3>
          <p className="text-gray-600">Collaborator</p>
           <p className="text-gray-600">chrys@orchestra-nexus.com</p>
          <p className="mt-2"><a href="https://www.linkedin.com/in/chrys-f%C3%A9-marty-niongolo-410770153/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">LinkedIn</a></p>
           {/* Add photo if link is provided later */}
        </div>
         <div className="bg-gray-100 p-4 rounded-lg">
          <h3 className="text-xl font-semibold">Robert Schröder</h3>
          <p className="text-gray-600">Initiator</p>
           <p className="text-gray-600">robert@orchestra-nexus.com</p>
          <p className="mt-2"><a href="https://www.linkedin.com/in/robert-schr%C3%B6der-aic?originalSubdomain=ch" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">LinkedIn</a></p>
           {/* Add photo if link is provided later */}
        </div>
      </div>

      <h2 className="text-2xl font-bold mb-4">Collaboration with orchestra-nexus</h2>
      <p className="mb-4">
        This project is a collaborative effort, with full usage rights, including distribution, granted to the orchestra-nexus GitHub organization.
        This collaboration is based on a contractual agreement ensuring the continued involvement of the project owner.
      </p>

    </div>
  );
};

export default AboutUs;
