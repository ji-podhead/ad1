import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Button } from "@/components/ui/button"; // Assuming Shadcn/ui components
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input';
import { Label } from "@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { toast } from 'sonner'; // Assuming sonner for toasts, or similar

interface User {
  id: number;
  email: string;
  is_admin: boolean;
  roles: string[];
}

const UserManagementPage: React.FC = () => {
  const { user: currentUser, isLoading: authLoading } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);

  // Dialog states
  const [isAddUserDialogOpen, setIsAddUserDialogOpen] = useState(false);
  const [isEditUserDialogOpen, setIsEditUserDialogOpen] = useState(false);
  const [isDeleteUserDialogOpen, setIsDeleteUserDialogOpen] = useState(false);

  const [selectedUser, setSelectedUser] = useState<User | null>(null);

  // Form states for Add/Edit
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [roles, setRoles] = useState(''); // Comma-separated string
  const [isAdmin, setIsAdmin] = useState(false);


  const fetchUsers = async () => {
    setIsLoadingUsers(true);
    try {
      const response = await fetch('/api/users');
      if (!response.ok) {
        throw new Error('Failed to fetch users');
      }
      const data = await response.json();
      setUsers(data);
    } catch (error) {
      console.error(error);
      toast.error('Failed to load users.');
    } finally {
      setIsLoadingUsers(false);
    }
  };

  useEffect(() => {
    if (currentUser?.is_admin) {
      fetchUsers();
    }
  }, [currentUser]);

  if (authLoading) {
    return <div className="container mx-auto p-4">Loading authentication details...</div>;
  }

  if (!currentUser?.is_admin) {
    return (
      <div className="container mx-auto p-4">
        <p className="text-red-500">Access Denied. You must be an administrator to view this page.</p>
      </div>
    );
  }

  // Handler for opening Add User dialog
  const handleAddUserOpen = () => {
    setEmail('');
    setPassword('');
    setRoles('');
    setIsAdmin(false);
    setIsAddUserDialogOpen(true);
  };

  // Handler for submitting Add User form
  const handleAddUserSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Email and password are required.");
      return;
    }
    try {
      const response = await fetch('/api/users/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          roles: roles.split(',').map(r => r.trim()).filter(r => r),
          is_admin: isAdmin
        }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to add user');
      }
      toast.success('User added successfully!');
      fetchUsers(); // Refresh list
      setIsAddUserDialogOpen(false);
    } catch (error: any) {
      toast.error(`Error: ${error.message}`);
    }
  };

  // Handler for opening Edit User dialog
  const handleEditUserOpen = (userToEdit: User) => {
    setSelectedUser(userToEdit);
    setEmail(userToEdit.email);
    setPassword(''); // Password is optional for edit, usually not pre-filled for security
    setRoles(userToEdit.roles.join(', '));
    setIsAdmin(userToEdit.is_admin);
    setIsEditUserDialogOpen(true);
  };

  // Handler for submitting Edit User form
  const handleEditUserSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;
    if (!email) {
      toast.error("Email cannot be empty.");
      return;
    }

    const payload: any = {
      email: email,
      roles: roles.split(',').map(r => r.trim()).filter(r => r),
      is_admin: isAdmin,
    };
    if (password) { // Only include password if user entered a new one
      payload.password = password;
    }

    try {
      const response = await fetch(`/api/users/${selectedUser.id}/set`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to update user');
      }
      toast.success('User updated successfully!');
      fetchUsers(); // Refresh list
      setIsEditUserDialogOpen(false);
      setSelectedUser(null);
    } catch (error: any) {
      toast.error(`Error: ${error.message}`);
    }
  };

  // Handler for opening Delete User dialog
  const handleDeleteUserOpen = (userToDelete: User) => {
    setSelectedUser(userToDelete);
    setIsDeleteUserDialogOpen(true);
  };

  // Handler for confirming Delete User
  const handleDeleteUserConfirm = async () => {
    if (!selectedUser) return;
    try {
      const response = await fetch(`/api/users/${selectedUser.id}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete user');
      }
      toast.success('User deleted successfully!');
      fetchUsers(); // Refresh list
      setIsDeleteUserDialogOpen(false);
      setSelectedUser(null);
    } catch (error: any) {
      toast.error(`Error: ${error.message}`);
    }
  };


  return (
    <div className="container mx-auto p-4">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">User Management</h1>
        <Button onClick={handleAddUserOpen}>Add User</Button>
      </div>

      {/* Add User Dialog */}
      <Dialog open={isAddUserDialogOpen} onOpenChange={setIsAddUserDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add New User</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddUserSubmit}>
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="email-add" className="text-right">Email</Label>
                <Input id="email-add" value={email} onChange={(e) => setEmail(e.target.value)} className="col-span-3" required />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="password-add" className="text-right">Password</Label>
                <Input id="password-add" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="col-span-3" required />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="roles-add" className="text-right">Roles (comma-sep)</Label>
                <Input id="roles-add" value={roles} onChange={(e) => setRoles(e.target.value)} className="col-span-3" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="isAdmin-add" className="text-right">Admin</Label>
                <Checkbox id="isAdmin-add" checked={isAdmin} onCheckedChange={(checked) => setIsAdmin(checked as boolean)} className="col-span-3" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setIsAddUserDialogOpen(false)}>Cancel</Button>
              <Button type="submit">Add User</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={isEditUserDialogOpen} onOpenChange={setIsEditUserDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User: {selectedUser?.email}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEditUserSubmit}>
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="email-edit" className="text-right">Email</Label>
                <Input id="email-edit" value={email} onChange={(e) => setEmail(e.target.value)} className="col-span-3" required/>
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="password-edit" className="text-right">New Password (optional)</Label>
                <Input id="password-edit" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="col-span-3" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="roles-edit" className="text-right">Roles (comma-sep)</Label>
                <Input id="roles-edit" value={roles} onChange={(e) => setRoles(e.target.value)} className="col-span-3" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="isAdmin-edit" className="text-right">Admin</Label>
                <Checkbox id="isAdmin-edit" checked={isAdmin} onCheckedChange={(checked) => setIsAdmin(checked as boolean)} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setIsEditUserDialogOpen(false)}>Cancel</Button>
              <Button type="submit">Save Changes</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete User Confirmation Dialog */}
      <Dialog open={isDeleteUserDialogOpen} onOpenChange={setIsDeleteUserDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete User</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete user {selectedUser?.email}? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDeleteUserDialogOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteUserConfirm}>Delete User</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>


      {isLoadingUsers ? (
        <p>Loading users...</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Admin</TableHead>
              <TableHead>Roles</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell>{user.email}</TableCell>
                <TableCell>{user.is_admin ? 'Yes' : 'No'}</TableCell>
                <TableCell>{user.roles.join(', ')}</TableCell>
                <TableCell>
                  <Button variant="outline" size="sm" onClick={() => handleEditUserOpen(user)} className="mr-2">Edit</Button>
                  <Button variant="destructive" size="sm" onClick={() => handleDeleteUserOpen(user)}>Delete</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
};

export default UserManagementPage;
