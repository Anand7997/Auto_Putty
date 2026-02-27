// API Configuration with debugging
console.log('🔍 Environment variables:', {
  VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
  VITE_ENV: import.meta.env.VITE_ENV,
  NODE_ENV: import.meta.env.NODE_ENV,
  MODE: import.meta.env.MODE
});

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://10.30.3.85:5000'; // Default fallback

console.log('🎯 Final API_BASE_URL:', API_BASE_URL);

// Helper function to build API URLs
export const buildApiUrl = (endpoint: string): string => {
  const fullUrl = `${API_BASE_URL}${endpoint}`;
  console.log('🔗 Building API URL:', endpoint, '->', fullUrl);
  return fullUrl;
};

// Export for easy access
export default {
  BASE_URL: API_BASE_URL,
  buildUrl: buildApiUrl
};
