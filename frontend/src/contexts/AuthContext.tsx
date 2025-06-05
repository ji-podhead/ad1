import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';

interface User {
  email: string | null;
  is_admin: boolean;
  roles: string[];
}

interface AuthContextType {
  user: User | null;
  setUser: (user: User | null) => void;
  isLoading: boolean; // To track if user info is being fetched
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUserState] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true); // Initially true

  // Attempt to load user from localStorage on initial load
  useEffect(() => {
    const storedUser = localStorage.getItem('loggedInUser');
    if (storedUser) {
      const parsedUser: { email: string } = JSON.parse(storedUser);
      if (parsedUser.email) {
        fetchUserInfo(parsedUser.email);
      } else {
        setIsLoading(false);
      }
    } else {
      setIsLoading(false);
    }
  }, []);

  const fetchUserInfo = async (email: string) => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/userinfo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (response.ok) {
        const data = await response.json();
        setUserState({ email, is_admin: data.is_admin, roles: data.roles });
      } else {
        console.error('Failed to fetch user info:', response.status);
        setUserState({ email, is_admin: false, roles: [] }); // Fallback
      }
    } catch (error) {
      console.error('Error fetching user info:', error);
      setUserState({ email, is_admin: false, roles: [] }); // Fallback
    } finally {
      setIsLoading(false);
    }
  };

  const setUser = (newUser: User | null) => {
    setUserState(newUser);
    if (newUser && newUser.email) {
      // When user is explicitly set (e.g., after login), fetch their full info
      // Also, update localStorage for persistence across sessions
      localStorage.setItem('loggedInUser', JSON.stringify({ email: newUser.email }));
      fetchUserInfo(newUser.email);
    } else {
      localStorage.removeItem('loggedInUser');
      setIsLoading(false); // No user, so not loading
    }
  };

  // This effect runs when `user` state changes, to re-fetch info if email is present but no roles/admin status
  // This is useful if setUser was called with just an email initially
  useEffect(() => {
    if (user && user.email && user.roles.length === 0 && !user.is_admin && !isLoading) {
        // Potentially, user was set with just email, and we need to fetch roles.
        // However, the current setUser implementation calls fetchUserInfo directly.
        // This effect can be a safeguard or be refined based on usage.
        // For now, let's ensure we don't fall into an infinite loop if fetchUserInfo fails.
        // The `isLoading` check helps prevent refetching if a fetch is already in progress.
    }
  }, [user, isLoading]);

  return (
    <AuthContext.Provider value={{ user, setUser, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
