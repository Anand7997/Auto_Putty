import { useState, useEffect } from 'react';
import { buildApiUrl } from '../config/api';

interface AuthorizationResult {
  authorized: boolean;
  loading: boolean;
  error: string | null;
}

export const useAuthorization = (functionName: string): AuthorizationResult => {
  const [authorized, setAuthorized] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const checkAuthorization = async () => {
      try {
        setLoading(true);
        setError(null);

        // Get current user email from localStorage
        const savedUser = localStorage.getItem('qfast_user');
        if (!savedUser) {
          setAuthorized(false);
          setLoading(false);
          return;
        }

        const user = JSON.parse(savedUser);
        const userEmail = user.email;

        const response = await fetch(buildApiUrl(`/api/user-authorization/${functionName}`), {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Email': userEmail,
          },
        });

        const result = await response.json();

        if (response.ok) {
          setAuthorized(result.authorized);
        } else {
          setError(result.error || 'Failed to check authorization');
          setAuthorized(false);
        }
      } catch (err: any) {
        setError(err.message || 'Network error');
        setAuthorized(false);
      } finally {
        setLoading(false);
      }
    };

    if (functionName) {
      checkAuthorization();
    }
  }, [functionName]);

  return { authorized, loading, error };
};

// Utility function to check authorization synchronously (for cases where we need immediate check)
export const checkAuthorization = async (functionName: string): Promise<boolean> => {
  try {
    const savedUser = localStorage.getItem('qfast_user');
    if (!savedUser) {
      return false;
    }

    const user = JSON.parse(savedUser);
    const userEmail = user.email;

    const response = await fetch(buildApiUrl(`/api/user-authorization/${functionName}`), {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Email': userEmail,
      },
    });

    const result = await response.json();
    return response.ok && result.authorized;
  } catch (err) {
    console.error('Authorization check failed:', err);
    return false;
  }
};