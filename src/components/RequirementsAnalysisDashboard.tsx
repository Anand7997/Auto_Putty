import React, { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  AlertTriangle,
  UserCheck,
  Settings,
  FileText,
  Upload,
  CheckCircle,
  XCircle,
  Download,
  File,
  Calendar,
  TestTube,
  Clock,
  PlayCircle,
  Trash2
} from 'lucide-react';
import { useAuthorization } from '@/hooks/useAuthorization';
import AuthorizeUsers from './AuthorizeUsers';
import AuthorizeFunctions from './AuthorizeFunctions';
import { API_BASE_URL } from '@/config/api';

interface User {
  id: number;
  username: string;
  email: string;
  role?: string;
  status?: string;
  last_login: string;
}

interface Execution {
  id: string;
  testRunId: string;
  status: 'passed' | 'failed' | 'running' | 'pending';
  startTime: string;
  endTime?: string;
  duration?: number;
  totalTests: number;
  passedTests: number;
  failedTests: number;
  environment: string;
  testSuite: string;
}

interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  message: string;
  context?: string;
}

interface RequirementsAnalysisDashboardProps {
  onBack?: () => void;
  onNext?: () => void;
  onFunctionSelect?: (func: any) => void;
  initialPage?: 'blocks' | 'authorize-users' | 'authorize-functions' | 'brd-upload' | 'brd-upload-document' | 'brd-upload-pdf' | 'brd-upload-excel' | 'test-analysis' | 'execution-list' | 'execution-log-analysis';
}

const RequirementsAnalysisDashboard: React.FC<RequirementsAnalysisDashboardProps> = ({ onBack, onNext, onFunctionSelect, initialPage = 'blocks' }) => {
  const [currentPage, setCurrentPage] = useState<'blocks' | 'authorize-users' | 'authorize-functions' | 'brd-upload' | 'brd-upload-document' | 'brd-upload-pdf' | 'brd-upload-excel' | 'test-analysis' | 'execution-list' | 'execution-log-analysis'>(initialPage);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [uploadStatus, setUploadStatus] = useState<{[key: string]: 'idle' | 'uploading' | 'success' | 'error'}>({
    document: 'idle',
    pdf: 'idle',
    excel: 'idle'
  });
  const [uploadMessages, setUploadMessages] = useState<{[key: string]: string}>({
    document: '',
    pdf: '',
    excel: ''
  });
  const [brdData, setBrdData] = useState<{[key: string]: {name: string, description: string, file: File | null}}>({
    document: {name: '', description: '', file: null},
    pdf: {name: '', description: '', file: null},
    excel: {name: '', description: '', file: null}
  });
  const [uploadedFiles, setUploadedFiles] = useState<{[key: string]: any[]}>({
    document: [],
    pdf: [],
    excel: []
  });

  // Test Analysis state
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);
  const [executionLogs, setExecutionLogs] = useState<LogEntry[]>([]);
  const [loadingExecutions, setLoadingExecutions] = useState(false);
  const [loadingLogs, setLoadingLogs] = useState(false);

  // Check authorization for requirements function
  const { authorized, loading: authLoading, error: authError } = useAuthorization('requirements');

  // Load current user from localStorage
  useEffect(() => {
    const savedUser = localStorage.getItem('qfast_user');
    if (savedUser) {
      try {
        const parsedUser = JSON.parse(savedUser);
        setCurrentUser(parsedUser);
      } catch (error) {
        console.error('Error parsing saved user:', error);
      }
    }
  }, []);

  useEffect(() => {
    setCurrentPage(initialPage);
  }, [initialPage]);

  // Load uploaded files when component mounts or current user changes
  useEffect(() => {
    if (currentUser?.email) {
      loadUploadedFiles('document');
      loadUploadedFiles('pdf');
      loadUploadedFiles('excel');
    }
  }, [currentUser]);

  // Load test executions when needed
  useEffect(() => {
    if (currentPage === 'execution-list') {
      loadTestExecutions();
    }
  }, [currentPage]);

  // Load execution logs when needed
  useEffect(() => {
    if (currentPage === 'execution-log-analysis' && selectedExecution) {
      loadExecutionLogs(selectedExecution.id);
    }
  }, [currentPage, selectedExecution]);

  // Helper function to map log levels
  const mapLogLevel = (status: string): 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' => {
    switch (status?.toUpperCase()) {
      case 'PASS':
      case 'SUCCESS':
        return 'INFO';
      case 'FAIL':
      case 'FAILED':
        return 'ERROR';
      case 'WARNING':
      case 'WARN':
        return 'WARN';
      case 'DEBUG':
      case 'DEBUG_INFO':
        return 'DEBUG';
      default:
        return 'INFO';
    }
  };

  // Load test executions from real API
  const loadTestExecutions = async () => {
    setLoadingExecutions(true);
    try {
      console.log('🔄 Loading REAL test executions from API...');
      const response = await fetch(`${API_BASE_URL}/api/results`);
      if (!response.ok) {
        throw new Error(`Failed to fetch executions: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('📊 Raw execution data received:', data);
      
      if (Array.isArray(data) && data.length > 0) {
        // Convert database results to execution format
        const executionMap = new Map();
        
        data.forEach((result: any) => {
          console.log('🔍 Processing execution result:', result);
          
          const executionKey = `${result.testcase_name || 'Unknown'}_${result.execution_date || result.created_date || Date.now()}`;
          
          if (!executionMap.has(executionKey)) {
            // Parse execution time to get duration in seconds
            let duration = 0;
            if (result.execution_time) {
              const timeMatch = result.execution_time.match(/(\d+):(\d+):(\d+)/);
              if (timeMatch) {
                const hours = parseInt(timeMatch[1]);
                const minutes = parseInt(timeMatch[2]);
                const seconds = parseInt(timeMatch[3]);
                duration = hours * 3600 + minutes * 60 + seconds;
              }
            }
            
            const execution: Execution = {
              id: result.id?.toString() || Date.now().toString(),
              testRunId: result.execution_id || result.testcase_name || 'Unknown',
              status: result.status === 'PASS' ? 'passed' : 
                     result.status === 'FAIL' ? 'failed' : 'running',
              startTime: result.created_date || result.execution_date || result.start_time || new Date().toISOString(),
              endTime: result.end_time || result.execution_date || 
                      (result.execution_time ? new Date().toISOString() : undefined),
              duration: duration > 0 ? duration : undefined,
              totalTests: result.total_steps || 1,
              passedTests: result.passed_steps || (result.status === 'PASS' ? 1 : 0),
              failedTests: result.failed_steps || (result.status === 'FAIL' ? 1 : 0),
              environment: result.environment || 'Unknown',
              testSuite: result.testsuitename || 'General'
            };
            
            executionMap.set(executionKey, execution);
          }
        });
        
        const realExecutions = Array.from(executionMap.values())
          .sort((a, b) => new Date(b.startTime).getTime() - new Date(a.startTime).getTime())
          .slice(0, 10); // Limit to most recent 10 executions
        
        console.log('✅ Processed real executions:', realExecutions);
        setExecutions(realExecutions);
      } else {
        console.log('ℹ️ No execution data found, showing empty state');
        setExecutions([]);
      }
    } catch (error) {
      console.error('❌ Error loading test executions:', error);
      setExecutions([]);
    } finally {
      setLoadingExecutions(false);
    }
  };

  // Load execution logs - FIXED: Now loads REAL logs from API
  const loadExecutionLogs = async (executionId: string) => {
    setLoadingLogs(true);
    try {
      console.log('🔄 Loading REAL execution logs for execution ID:', executionId);
      
      const response = await fetch(`${API_BASE_URL}/api/execution-details/${executionId}`, {
        method: 'GET',
        headers: {
          'X-User-Email': currentUser?.email || '',
        },
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch logs: ${response.status}`);
      }
      
      const data = await response.json();
      console.log('📊 Received execution details:', data);
      
      // Convert execution details to log format
      const realLogs: LogEntry[] = [];
      
      // Add test execution metadata as logs
      if (data.execution_details && Array.isArray(data.execution_details)) {
        data.execution_details.forEach((detail: any, index: number) => {
          realLogs.push({
            id: `step-${index + 1}`,
            timestamp: detail.step_timestamp || detail.timestamp || new Date().toISOString(),
            level: mapLogLevel(detail.step_status || detail.status || 'INFO'),
            message: detail.step_description || detail.message || detail.description || `Step ${index + 1}: ${detail.action_type || detail.context || 'Test step'}`,
            context: detail.context || detail.module_name || detail.source || 'TestStep'
          });
        });
      }
      
      // If no execution details, show basic execution info
      if (realLogs.length === 0) {
        realLogs.push({
          id: 'exec-start',
          timestamp: data.created_date || data.start_time || new Date().toISOString(),
          level: 'INFO',
          message: `Test execution started: ${data.testcase_name || 'Unknown test case'}`,
          context: 'TestRunner'
        });
        
        if (data.status) {
          realLogs.push({
            id: 'exec-end',
            timestamp: data.end_time || new Date().toISOString(),
            level: data.status === 'PASS' ? 'INFO' : 'ERROR',
            message: `Test execution ${data.status === 'PASS' ? 'completed successfully' : 'failed'}: ${data.testcase_name || 'Unknown test case'}`,
            context: 'TestExecutor'
          });
        }
        
        // If there are step details in the main response
        if (data.step_details && Array.isArray(data.step_details)) {
          data.step_details.forEach((step: any, index: number) => {
            realLogs.push({
              id: `step-${index + 1}`,
              timestamp: step.timestamp || new Date().toISOString(),
              level: mapLogLevel(step.status || 'INFO'),
              message: step.description || step.message || `Step ${index + 1}: ${step.action || 'Test action'}`,
              context: step.context || step.module || 'TestStep'
            });
          });
        }
      }
      
      console.log('✅ Processed real execution logs:', realLogs);
      setExecutionLogs(realLogs);
      
    } catch (apiError) {
      console.error('❌ API call failed, falling back to basic execution info:', apiError);
      
      // Fallback: show basic execution information from the selected execution
      const fallbackLogs: LogEntry[] = [
        {
          id: 'exec-start',
          timestamp: selectedExecution.startTime,
          level: 'INFO',
          message: `Test execution started: ${selectedExecution.testRunId}`,
          context: 'TestRunner'
        },
        {
          id: 'exec-status',
          timestamp: selectedExecution.endTime || selectedExecution.startTime,
          level: selectedExecution.status === 'passed' ? 'INFO' : 'ERROR',
          message: `Test execution ${selectedExecution.status}: ${selectedExecution.testRunId} - ${selectedExecution.passedTests} passed, ${selectedExecution.failedTests} failed`,
          context: 'TestExecutor'
        }
      ];
      
      setExecutionLogs(fallbackLogs);
    } finally {
      setLoadingLogs(false);
    }
  };

  // Get log level color
  const getLogLevelColor = (level: string) => {
    switch (level) {
      case 'ERROR': return 'text-red-600 bg-red-50';
      case 'WARN': return 'text-yellow-600 bg-yellow-50';
      case 'INFO': return 'text-blue-600 bg-blue-50';
      case 'DEBUG': return 'text-gray-600 bg-gray-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  // Get execution status color
  const getExecutionStatusColor = (status: string) => {
    switch (status) {
      case 'passed': return 'text-green-600 bg-green-50';
      case 'failed': return 'text-red-600 bg-red-50';
      case 'running': return 'text-blue-600 bg-blue-50';
      case 'pending': return 'text-yellow-600 bg-yellow-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  // Handle input changes
  const handleInputChange = (fileType: string, field: 'name' | 'description', value: string) => {
    setBrdData(prev => ({
      ...prev,
      [fileType]: {
        ...prev[fileType],
        [field]: value
      }
    }));
  };

  // Handle file selection
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>, fileType: string) => {
    const file = event.target.files?.[0];
    if (file) {
      setBrdData(prev => ({
        ...prev,
        [fileType]: {
          ...prev[fileType],
          file: file
        }
      }));
    }
  };

  // Handle save/upload
  const handleSave = async (fileType: string) => {
    const data = brdData[fileType];
    if (!data.file || !data.name.trim()) {
      setUploadStatus(prev => ({ ...prev, [fileType]: 'error' }));
      setUploadMessages(prev => ({ ...prev, [fileType]: 'Please provide a name and select a file' }));
      return;
    }

    setUploadStatus(prev => ({ ...prev, [fileType]: 'uploading' }));
    setUploadMessages(prev => ({ ...prev, [fileType]: 'Uploading...' }));

    try {
      const formData = new FormData();
      formData.append('file', data.file);
      formData.append('file_type', fileType);
      formData.append('name', data.name);
      formData.append('description', data.description);

      const response = await fetch(`${API_BASE_URL}/api/brd/upload`, {
        method: 'POST',
        headers: {
          'X-User-Email': currentUser?.email || '',
        },
        body: formData,
      });

      const result = await response.json();

      if (response.ok) {
        setUploadStatus(prev => ({ ...prev, [fileType]: 'success' }));
        setUploadMessages(prev => ({ ...prev, [fileType]: `Successfully uploaded ${data.file.name}` }));

        // Clear the form after successful upload
        setBrdData(prev => ({
          ...prev,
          [fileType]: {name: '', description: '', file: null}
        }));

        // Reset file input
        const fileInput = document.getElementById(`file-input-${fileType}`) as HTMLInputElement;
        if (fileInput) fileInput.value = '';

        // Refresh the uploaded files list
        await loadUploadedFiles(fileType);

      } else {
        throw new Error(result.error || 'Upload failed');
      }
    } catch (error) {
      setUploadStatus(prev => ({ ...prev, [fileType]: 'error' }));
      setUploadMessages(prev => ({ ...prev, [fileType]: error instanceof Error ? error.message : 'Upload failed' }));
    }
  };

  // Load uploaded files for a specific file type
  const loadUploadedFiles = async (fileType: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/brd/files`, {
        method: 'GET',
        headers: {
          'X-User-Email': currentUser?.email || '',
        },
      });

      if (response.ok) {
        const result = await response.json();
        const files = result.files || [];
        // Filter files by type
        const filteredFiles = files.filter((file: any) => file.file_type === fileType);
        setUploadedFiles(prev => ({
          ...prev,
          [fileType]: filteredFiles
        }));
      }
    } catch (error) {
      console.error('Error loading uploaded files:', error);
    }
  };

  // Handle file download
  const handleDownload = async (fileId: number, fileName: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/brd/download/${fileId}`, {
        method: 'GET',
        headers: {
          'X-User-Email': currentUser?.email || '',
        },
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        console.error('Download failed');
      }
    } catch (error) {
      console.error('Error downloading file:', error);
    }
  };

  // Handle file delete
  const handleDelete = async (fileId: number, fileType: string) => {
    if (!confirm('Are you sure you want to delete this file? This action cannot be undone.')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/brd/delete/${fileId}`, {
        method: 'DELETE',
        headers: {
          'X-User-Email': currentUser?.email || '',
        },
      });

      if (response.ok) {
        // Refresh the uploaded files list
        await loadUploadedFiles(fileType);
      } else {
        console.error('Delete failed');
        alert('Failed to delete the file. Please try again.');
      }
    } catch (error) {
      console.error('Error deleting file:', error);
      alert('Error deleting file. Please try again.');
    }
  };

  // Format file size
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // Format duration
  const formatDuration = (seconds: number) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  // Show loading while checking authorization
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Checking authorization...</p>
        </div>
      </div>
    );
  }

  // Show error if authorization check failed
  if (authError) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-600">Error checking authorization: {authError}</p>
        </div>
      </div>
    );
  }

  // Show access denied if not authorized
  if (!authorized) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Access Denied</h2>
          <p className="text-gray-600">You are not allowed to access this function.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Requirements Analysis Dashboard</h2>
          <p className="text-gray-600 mb-8">Manage user authorizations and function permissions</p>
        </div>

        {/* Content */}
        <div className="bg-white shadow rounded-lg">
          {currentPage === 'blocks' && (
            <div className="p-8">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">Requirements Analysis</h2>
              <p className="text-gray-600 mb-8">Select an option to manage authorizations</p>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <Card
                  className="cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => setCurrentPage('brd-upload')}
                >
                  <CardContent className="p-6">
                    <div className="flex items-center space-x-4">
                      <FileText className="w-8 h-8 text-purple-600" />
                      <div>
                        <h3 className="text-lg font-semibold">Upload Document</h3>
                        <p className="text-gray-600">Upload Business Requirements Documents</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card
                  className="cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => setCurrentPage('authorize-users')}
                >
                  <CardContent className="p-6">
                    <div className="flex items-center space-x-4">
                      <UserCheck className="w-8 h-8 text-blue-600" />
                      <div>
                        <h3 className="text-lg font-semibold">Authorize Users</h3>
                        <p className="text-gray-600">Manage user authorizations for requirements analysis</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card
                  className="cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => setCurrentPage('authorize-functions')}
                >
                  <CardContent className="p-6">
                    <div className="flex items-center space-x-4">
                      <Settings className="w-8 h-8 text-green-600" />
                      <div>
                        <h3 className="text-lg font-semibold">Authorize Functions</h3>
                        <p className="text-gray-600">Configure function authorizations</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                <Card
                  className="cursor-pointer hover:shadow-lg transition-shadow"
                  onClick={() => setCurrentPage('test-analysis')}
                >
                  <CardContent className="p-6">
                    <div className="flex items-center space-x-4">
                      <TestTube className="w-8 h-8 text-orange-600" />
                      <div>
                        <h3 className="text-lg font-semibold">Test Analysis</h3>
                        <p className="text-gray-600">View test executions and logs analysis</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}
          {currentPage === 'authorize-users' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('blocks')} className="mb-2">
                  ← Back to Options
                </Button>
              </div>
              <div className="p-6">
                {currentUser ? (
                  <AuthorizeUsers currentUser={currentUser} />
                ) : (
                  <div className="text-center py-8">
                    <p className="text-gray-500">Loading user information...</p>
                  </div>
                )}
              </div>
            </div>
          )}
          {currentPage === 'brd-upload' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('blocks')} className="mb-2">
                  ← Back to Options
                </Button>
              </div>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">BRD Upload</h2>
                <p className="text-gray-600 mb-8">Select the file format to upload</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <Card
                    className="cursor-pointer hover:shadow-lg transition-shadow"
                    onClick={() => setCurrentPage('brd-upload-document')}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-center space-x-4">
                        <FileText className="w-8 h-8 text-blue-600" />
                        <div>
                          <h3 className="text-lg font-semibold">Document</h3>
                          <p className="text-gray-600">Upload .doc or .docx files</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                  <Card
                    className="cursor-pointer hover:shadow-lg transition-shadow"
                    onClick={() => setCurrentPage('brd-upload-pdf')}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-center space-x-4">
                        <FileText className="w-8 h-8 text-red-600" />
                        <div>
                          <h3 className="text-lg font-semibold">PDF</h3>
                          <p className="text-gray-600">Upload .pdf files</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                  <Card
                    className="cursor-pointer hover:shadow-lg transition-shadow"
                    onClick={() => setCurrentPage('brd-upload-excel')}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-center space-x-4">
                        <FileText className="w-8 h-8 text-green-600" />
                        <div>
                          <h3 className="text-lg font-semibold">Excel</h3>
                          <p className="text-gray-600">Upload .xlsx or .xls files</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}
          {currentPage === 'brd-upload-document' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('brd-upload')} className="mb-2">
                  ← Back to BRD Upload
                </Button>
              </div>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">Upload Document Files</h2>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Upload</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      <tr>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <input
                            type="text"
                            placeholder="Enter document name"
                            value={brdData.document.name}
                            onChange={(e) => handleInputChange('document', 'name', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <input
                            type="text"
                            placeholder="Enter description"
                            value={brdData.document.description}
                            onChange={(e) => handleInputChange('document', 'description', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          <div className="flex flex-col space-y-2">
                            <input
                              id="file-input-document"
                              type="file"
                              accept=".doc,.docx"
                              onChange={(e) => handleFileSelect(e, 'document')}
                              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                            />
                            <Button
                              onClick={() => handleSave('document')}
                              disabled={uploadStatus.document === 'uploading'}
                              className="w-full bg-blue-600 hover:bg-blue-700 text-white"
                            >
                              {uploadStatus.document === 'uploading' ? 'Uploading...' : 'Save'}
                            </Button>
                            {uploadMessages.document && (
                              <div className={`text-sm ${uploadStatus.document === 'success' ? 'text-green-600' : uploadStatus.document === 'error' ? 'text-red-600' : 'text-gray-600'}`}>
                                {uploadMessages.document}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Uploaded Files List */}
                {uploadedFiles.document.length > 0 && (
                  <div className="mt-8">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Uploaded Document Files</h3>
                    <div className="space-y-3">
                      {uploadedFiles.document.map((file) => (
                        <div key={file.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
                          <div className="flex items-center space-x-3">
                            <File className="w-5 h-5 text-blue-600" />
                            <div>
                              <p className="font-medium text-gray-900">{file.file_name}</p>
                              <p className="text-sm text-gray-600">{file.original_name}</p>
                              <div className="flex items-center space-x-4 mt-1">
                                <span className="text-xs text-gray-500">{formatFileSize(file.file_size)}</span>
                                <div className="flex items-center space-x-1">
                                  <Calendar className="w-3 h-3 text-gray-400" />
                                  <span className="text-xs text-gray-500">
                                    {new Date(file.uploaded_at).toLocaleDateString()}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            <Button
                              onClick={() => handleDownload(file.id, file.original_name)}
                              variant="outline"
                              size="sm"
                              className="flex items-center space-x-2"
                            >
                              <Download className="w-4 h-4" />
                              <span>Download</span>
                            </Button>
                            <Button
                              onClick={() => handleDelete(file.id, 'document')}
                              variant="outline"
                              size="sm"
                              className="flex items-center space-x-2 text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                              <Trash2 className="w-4 h-4" />
                              <span>Delete</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {currentPage === 'brd-upload-pdf' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('brd-upload')} className="mb-2">
                  ← Back to BRD Upload
                </Button>
              </div>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">Upload PDF Files</h2>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Upload</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      <tr>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <input
                            type="text"
                            placeholder="Enter PDF name"
                            value={brdData.pdf.name}
                            onChange={(e) => handleInputChange('pdf', 'name', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <input
                            type="text"
                            placeholder="Enter description"
                            value={brdData.pdf.description}
                            onChange={(e) => handleInputChange('pdf', 'description', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          <div className="flex flex-col space-y-2">
                            <input
                              id="file-input-pdf"
                              type="file"
                              accept=".pdf"
                              onChange={(e) => handleFileSelect(e, 'pdf')}
                              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-red-50 file:text-red-700 hover:file:bg-red-100"
                            />
                            <Button
                              onClick={() => handleSave('pdf')}
                              disabled={uploadStatus.pdf === 'uploading'}
                              className="w-full bg-red-600 hover:bg-red-700 text-white"
                            >
                              {uploadStatus.pdf === 'uploading' ? 'Uploading...' : 'Save'}
                            </Button>
                            {uploadMessages.pdf && (
                              <div className={`text-sm ${uploadStatus.pdf === 'success' ? 'text-green-600' : uploadStatus.pdf === 'error' ? 'text-red-600' : 'text-gray-600'}`}>
                                {uploadMessages.pdf}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Uploaded Files List */}
                {uploadedFiles.pdf.length > 0 && (
                  <div className="mt-8">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Uploaded PDF Files</h3>
                    <div className="space-y-3">
                      {uploadedFiles.pdf.map((file) => (
                        <div key={file.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
                          <div className="flex items-center space-x-3">
                            <File className="w-5 h-5 text-red-600" />
                            <div>
                              <p className="font-medium text-gray-900">{file.file_name}</p>
                              <p className="text-sm text-gray-600">{file.original_name}</p>
                              <div className="flex items-center space-x-4 mt-1">
                                <span className="text-xs text-gray-500">{formatFileSize(file.file_size)}</span>
                                <div className="flex items-center space-x-1">
                                  <Calendar className="w-3 h-3 text-gray-400" />
                                  <span className="text-xs text-gray-500">
                                    {new Date(file.uploaded_at).toLocaleDateString()}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            <Button
                              onClick={() => handleDownload(file.id, file.original_name)}
                              variant="outline"
                              size="sm"
                              className="flex items-center space-x-2"
                            >
                              <Download className="w-4 h-4" />
                              <span>Download</span>
                            </Button>
                            <Button
                              onClick={() => handleDelete(file.id, 'pdf')}
                              variant="outline"
                              size="sm"
                              className="flex items-center space-x-2 text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                              <Trash2 className="w-4 h-4" />
                              <span>Delete</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {currentPage === 'brd-upload-excel' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('brd-upload')} className="mb-2">
                  ← Back to BRD Upload
                </Button>
              </div>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">Upload Excel Files</h2>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Upload</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      <tr>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <input
                            type="text"
                            placeholder="Enter Excel name"
                            value={brdData.excel.name}
                            onChange={(e) => handleInputChange('excel', 'name', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <input
                            type="text"
                            placeholder="Enter description"
                            value={brdData.excel.description}
                            onChange={(e) => handleInputChange('excel', 'description', e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          <div className="flex flex-col space-y-2">
                            <input
                              id="file-input-excel"
                              type="file"
                              accept=".xlsx,.xls"
                              onChange={(e) => handleFileSelect(e, 'excel')}
                              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-green-50 file:text-green-700 hover:file:bg-green-100"
                            />
                            <Button
                              onClick={() => handleSave('excel')}
                              disabled={uploadStatus.excel === 'uploading'}
                              className="w-full bg-green-600 hover:bg-green-700 text-white"
                            >
                              {uploadStatus.excel === 'uploading' ? 'Uploading...' : 'Save'}
                            </Button>
                            {uploadMessages.excel && (
                              <div className={`text-sm ${uploadStatus.excel === 'success' ? 'text-green-600' : uploadStatus.excel === 'error' ? 'text-red-600' : 'text-gray-600'}`}>
                                {uploadMessages.excel}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Uploaded Files List */}
                {uploadedFiles.excel.length > 0 && (
                  <div className="mt-8">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Uploaded Excel Files</h3>
                    <div className="space-y-3">
                      {uploadedFiles.excel.map((file) => (
                        <div key={file.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
                          <div className="flex items-center space-x-3">
                            <File className="w-5 h-5 text-green-600" />
                            <div>
                              <p className="font-medium text-gray-900">{file.file_name}</p>
                              <p className="text-sm text-gray-600">{file.original_name}</p>
                              <div className="flex items-center space-x-4 mt-1">
                                <span className="text-xs text-gray-500">{formatFileSize(file.file_size)}</span>
                                <div className="flex items-center space-x-1">
                                  <Calendar className="w-3 h-3 text-gray-400" />
                                  <span className="text-xs text-gray-500">
                                    {new Date(file.uploaded_at).toLocaleDateString()}
                                  </span>
                                </div>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            <Button
                              onClick={() => handleDownload(file.id, file.original_name)}
                              variant="outline"
                              size="sm"
                              className="flex items-center space-x-2"
                            >
                              <Download className="w-4 h-4" />
                              <span>Download</span>
                            </Button>
                            <Button
                              onClick={() => handleDelete(file.id, 'excel')}
                              variant="outline"
                              size="sm"
                              className="flex items-center space-x-2 text-red-600 hover:text-red-700 hover:bg-red-50"
                            >
                              <Trash2 className="w-4 h-4" />
                              <span>Delete</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
          {currentPage === 'authorize-functions' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('blocks')} className="mb-2">
                  ← Back to Options
                </Button>
              </div>
              <div className="p-6">
                <AuthorizeFunctions onFunctionSelect={onFunctionSelect} />
              </div>
            </div>
          )}
          {currentPage === 'test-analysis' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('blocks')} className="mb-2">
                  ← Back to Options
                </Button>
              </div>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">Test Analysis</h2>
                <p className="text-gray-600 mb-8">View and analyze test executions</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <Card
                    className="cursor-pointer hover:shadow-lg transition-shadow"
                    onClick={() => setCurrentPage('execution-list')}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-center space-x-4">
                        <PlayCircle className="w-8 h-8 text-blue-600" />
                        <div>
                          <h3 className="text-lg font-semibold">Recent Executions</h3>
                          <p className="text-gray-600">View recent test executions with run IDs</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                  <Card
                    className="cursor-pointer hover:shadow-lg transition-shadow opacity-50"
                  >
                    <CardContent className="p-6">
                      <div className="flex items-center space-x-4">
                        <FileText className="w-8 h-8 text-green-600" />
                        <div>
                          <h3 className="text-lg font-semibold">Log Analysis</h3>
                          <p className="text-gray-600">Select an execution to view log analysis</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}
          {currentPage === 'execution-list' && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('test-analysis')} className="mb-2">
                  ← Back to Test Analysis
                </Button>
              </div>
              <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900 mb-6">Recent Test Executions</h2>
                <p className="text-gray-600 mb-8">Click on any execution to view detailed log analysis</p>
                
                {loadingExecutions ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading executions...</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {executions.map((execution) => (
                      <Card
                        key={execution.id}
                        className="cursor-pointer hover:shadow-lg transition-shadow"
                        onClick={() => {
                          setSelectedExecution(execution);
                          setCurrentPage('execution-log-analysis');
                        }}
                      >
                        <CardContent className="p-6">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center space-x-4">
                              <div className="flex items-center space-x-2">
                                <Clock className="w-5 h-5 text-gray-400" />
                                <span className="text-sm text-gray-600">
                                  {new Date(execution.startTime).toLocaleString()}
                                </span>
                              </div>
                              <div className={`px-2 py-1 rounded-full text-xs font-medium ${getExecutionStatusColor(execution.status)}`}>
                                {execution.status.toUpperCase()}
                              </div>
                            </div>
                            <div className="text-right">
                              <p className="font-semibold text-gray-900">{execution.testRunId}</p>
                              <p className="text-sm text-gray-600">{execution.testSuite}</p>
                            </div>
                          </div>
                          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div className="text-center">
                              <p className="text-lg font-semibold text-gray-900">{execution.totalTests}</p>
                              <p className="text-sm text-gray-600">Total Tests</p>
                            </div>
                            <div className="text-center">
                              <p className="text-lg font-semibold text-green-600">{execution.passedTests}</p>
                              <p className="text-sm text-gray-600">Passed</p>
                            </div>
                            <div className="text-center">
                              <p className="text-lg font-semibold text-red-600">{execution.failedTests}</p>
                              <p className="text-sm text-gray-600">Failed</p>
                            </div>
                            <div className="text-center">
                              <p className="text-lg font-semibold text-gray-900">
                                {execution.duration ? formatDuration(execution.duration) : '--'}
                              </p>
                              <p className="text-sm text-gray-600">Duration</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
          {currentPage === 'execution-log-analysis' && selectedExecution && (
            <div>
              <div className="p-4 border-b border-gray-200">
                <Button variant="ghost" onClick={() => setCurrentPage('execution-list')} className="mb-2">
                  ← Back to Execution List
                </Button>
              </div>
              <div className="p-6">
                <div className="mb-6">
                  <h2 className="text-2xl font-bold text-gray-900 mb-2">Execution Log Analysis</h2>
                  <div className="flex items-center space-x-4">
                    <p className="text-lg font-semibold text-blue-600">{selectedExecution.testRunId}</p>
                    <div className={`px-2 py-1 rounded-full text-xs font-medium ${getExecutionStatusColor(selectedExecution.status)}`}>
                      {selectedExecution.status.toUpperCase()}
                    </div>
                    <span className="text-gray-600">{selectedExecution.environment}</span>
                    <span className="text-gray-600">{selectedExecution.testSuite}</span>
                  </div>
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-300px)]">
                  {/* Logs Panel */}
                  <div className="bg-gray-900 rounded-lg p-4 overflow-y-auto">
                    <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
                      <FileText className="w-5 h-5 mr-2" />
                      Execution Logs
                    </h3>
                    {loadingLogs ? (
                      <div className="text-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
                        <p className="text-gray-400">Loading logs...</p>
                      </div>
                    ) : (
                      <div className="space-y-2 font-mono text-sm">
                        {executionLogs.map((log) => (
                          <div key={log.id} className="flex items-start space-x-3 p-2 hover:bg-gray-800 rounded">
                            <span className="text-gray-400 text-xs mt-0.5 whitespace-nowrap">
                              {new Date(log.timestamp).toLocaleTimeString()}
                            </span>
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${getLogLevelColor(log.level)}`}>
                              {log.level}
                            </span>
                            <span className="text-gray-300">{log.message}</span>
                            {log.context && (
                              <span className="text-gray-500 text-xs">[{log.context}]</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Log Meaning Panel */}
                  <div className="bg-white border rounded-lg p-4 overflow-y-auto">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <TestTube className="w-5 h-5 mr-2" />
                      Log Level Meanings
                    </h3>
                    <div className="space-y-4">
                      <div className="border-l-4 border-red-400 pl-4">
                        <h4 className="font-semibold text-red-600">ERROR (Red)</h4>
                        <p className="text-sm text-gray-600">Critical errors that cause test failures or prevent execution from continuing. These indicate serious problems that need immediate attention.</p>
                      </div>
                      <div className="border-l-4 border-yellow-400 pl-4">
                        <h4 className="font-semibold text-yellow-600">WARN (Yellow)</h4>
                        <p className="text-sm text-gray-600">Warnings that may indicate potential issues but don't necessarily cause test failures. These suggest areas that might need investigation.</p>
                      </div>
                      <div className="border-l-4 border-blue-400 pl-4">
                        <h4 className="font-semibold text-blue-600">INFO (Blue)</h4>
                        <p className="text-sm text-gray-600">General information about test execution progress, setup, and completion. These provide context about what the test is doing.</p>
                      </div>
                      <div className="border-l-4 border-gray-400 pl-4">
                        <h4 className="font-semibold text-gray-600">DEBUG (Gray)</h4>
                        <p className="text-sm text-gray-600">Detailed debugging information for troubleshooting purposes. These contain low-level details about test execution.</p>
                      </div>
                    </div>
                    
                    <div className="mt-6 p-4 bg-blue-50 rounded-lg">
                      <h4 className="font-semibold text-blue-800 mb-2">Log Analysis Tips</h4>
                      <ul className="text-sm text-blue-700 space-y-1">
                        <li>• Look for ERROR logs first - these indicate failures</li>
                        <li>• Check WARN logs for potential issues</li>
                        <li>• Use timestamps to trace execution flow</li>
                        <li>• Context information helps identify which component generated the log</li>
                        <li>• Pay attention to pattern in log entries for recurring issues</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RequirementsAnalysisDashboard;
