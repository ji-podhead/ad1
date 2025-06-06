import React, { useState, useEffect } from "react";

const allRoles = ["Lesen", "Schreiben", "Validieren", "Runterladen"];

const IPAMPage: React.FC = () => {
  const [users, setUsers] = useState<any[]>([]);
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/users")
      .then((res) => res.json())
      .then(setUsers);
  }, []);

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.endsWith("@gmail.com")) {
      setError("Nur Google Mail-Adressen erlaubt.");
      return;
    }
    if (users.some((u) => u.email === email)) {
      setError("User existiert bereits.");
      return;
    }
    try {
      const res = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, roles, is_admin: false }),
      });
      if (!res.ok) throw new Error("Fehler beim Anlegen des Users");
      const newUser = await res.json();
      setUsers([...users, newUser]);
      setEmail("");
      setRoles([]);
      setError("");
    } catch (err: any) {
      setError(err.message || "Unbekannter Fehler");
    }
  };

  const handleRoleChange = (role: string, checked: boolean) => {
    setRoles((prev) =>
      checked ? [...prev, role] : prev.filter((r) => r !== role)
    );
  };

  const handleAdminToggle = (idx: number) => {
    setUsers((prev) =>
      prev.map((u, i) =>
        i === idx ? { ...u, isAdmin: !u.isAdmin } : u
      )
    );
  };

  const handleUserRoleChange = (idx: number, role: string, checked: boolean) => {
    setUsers((prev) =>
      prev.map((u, i) =>
        i === idx
          ? {
              ...u,
              roles: checked
                ? [...u.roles, role]
                : u.roles.filter((r) => r !== role),
            }
          : u
      )
    );
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-4">IPAM – User Management</h1>
      <form onSubmit={handleAddUser} className="mb-6 bg-white rounded shadow p-4 flex flex-col gap-2">
        <label className="font-medium">Google Mail-Adresse</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border rounded px-3 py-2"
          placeholder="user@gmail.com"
          required
        />
        <div className="flex gap-4 mt-2">
          {allRoles.map((role) => (
            <label key={role} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={roles.includes(role)}
                onChange={(e) => handleRoleChange(role, e.target.checked)}
              />
              {role}
            </label>
          ))}
        </div>
        {error && <div className="text-red-600 text-sm mt-1">{error}</div>}
        <button type="submit" className="mt-2 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">User hinzufügen</button>
      </form>
      <h2 className="text-xl font-semibold mb-2">Bestehende User</h2>
      <table className="w-full bg-white rounded shadow text-left">
        <thead>
          <tr className="bg-gray-100">
            <th className="p-2">E-Mail</th>
            <th className="p-2">Rollen</th>
            <th className="p-2">Admin</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user, idx) => (
            <tr key={user.email} className="border-t">
              <td className="p-2 font-mono">{user.email}</td>
              <td className="p-2">
                <div className="flex gap-2 flex-wrap">
                  {allRoles.map((role) => (
                    <label key={role} className="flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={user.roles.includes(role)}
                        onChange={(e) => handleUserRoleChange(idx, role, e.target.checked)}
                      />
                      {role}
                    </label>
                  ))}
                </div>
              </td>
              <td className="p-2">
                <input
                  type="checkbox"
                  checked={user.isAdmin}
                  onChange={() => handleAdminToggle(idx)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default IPAMPage;
