import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Plus, Edit, Trash2, TestTube, ArrowRight, ArrowLeft, Database, Eye, List, Save, FileText, Download, Search, Filter, X } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { buildApiUrl } from '@/config/api';
import { formatExecutionDate } from '@/lib/utils';
import TestStepsGrid, { TestStepsGridRef } from './TestStepsGrid';

// Global timeout for auto-save debouncing
declare global {
    interface Window {
        testStepsAutoSaveTimeout: NodeJS.Timeout;
    }
}

interface TestCase {
    id: number;
    testcase_id: string;
    name: string;
    description: string;
    project_id: number;
    module_id: number;
    project_name?: string;
    module_name?: string;
    project?: string;
    module?: string;
    created_date: string;
    status: string;
    priority: string;
}

interface TestStep {
    id: number;
    tc_id: string;
    step_no: number;
    test_step_description: string;
    page?: string;
    element_name: string;
    action_type: string;
    xpath: string;
    values: string;
}

interface TestCaseDashboardProps {
    selectedProject: any;
    selectedModule: any;
    selectedTestSuite?: any;
    onTestCaseSelect?: (testCase: TestCase) => void;
    onNext?: () => void;
    onBack?: () => void;
    readOnlyMode?: boolean;
    highlightTestCase?: string; // Name of test case to highlight (from development sync)
    developmentMode?: boolean; // Special mode for automation development
}

const TestCaseDashboard: React.FC<TestCaseDashboardProps> = ({
    selectedProject,
    selectedModule,
    selectedTestSuite,
    onTestCaseSelect,
    onNext,
    onBack,
    readOnlyMode = false,
    highlightTestCase,
    developmentMode = false
}) => {
    const [testCases, setTestCases] = useState<TestCase[]>([]);
    const [isLoadingTestCases, setIsLoadingTestCases] = useState(false);
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [selectedTestCase, setSelectedTestCase] = useState<TestCase | null>(null);
    const [editingTestCase, setEditingTestCase] = useState<TestCase | null>(null);
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        priority: 'Medium'
    });
    const [showTestSteps, setShowTestSteps] = useState(false);
    const [testSteps, setTestSteps] = useState<TestStep[]>([]);
    const [viewingTestCase, setViewingTestCase] = useState<TestCase | null>(null);
    const [editingSteps, setEditingSteps] = useState(false);
    const [isLoadingSteps, setIsLoadingSteps] = useState(false); // Track when steps are being loaded from DB
    const testStepsGridRef = useRef<TestStepsGridRef>(null);
    const { toast } = useToast();

    // BRD Selection state
    const [brdFiles, setBrdFiles] = useState<any[]>([]);
    const [brdPanelOpen, setBrdPanelOpen] = useState(false);
    const [brdSearchTerm, setBrdSearchTerm] = useState('');
    const [brdFilterType, setBrdFilterType] = useState<string>('all');
    const [selectedBrdFiles, setSelectedBrdFiles] = useState<any[]>([]);

    useEffect(() => {
        if (selectedModule) {
            fetchTestCases();
        }
    }, [selectedModule]);

    // Cleanup auto-save timeout on unmount
    useEffect(() => {
        return () => {
            if (window.testStepsAutoSaveTimeout) {
                clearTimeout(window.testStepsAutoSaveTimeout);
            }
        };
    }, []);

    const fetchTestCases = async () => {
        try {
            setIsLoadingTestCases(true);
            console.log('Current selectedModule:', selectedModule);
            console.log('Current selectedProject:', selectedProject);
            
            const startTime = performance.now();
            
            // Use the new optimized bulk endpoint for a single API call
            const suiteTypes = ['general', 'automation', 'development', 'smoke', 'sanity', 'regression'];
            const suiteTypesParam = suiteTypes.join(',');
            
            console.log('Fetching test cases using optimized bulk endpoint...');
            
            try {
                const apiUrl = buildApiUrl(`/api/testcases/bulk?suite_types=${encodeURIComponent(suiteTypesParam)}&module_id=${selectedModule.id}`);
                console.log('Bulk API URL:', apiUrl);
                
                const response = await fetch(apiUrl);
                if (response.ok) {
                    const data = await response.json();
                    const testCases = data.test_cases || [];
                    
                    const endTime = performance.now();
                    console.log(`✅ Bulk fetch: Found ${testCases.length} test cases in ${(endTime - startTime).toFixed(2)}ms`);
                    console.log(`Suite types queried: ${data.suite_types_queried?.join(', ')}`);
                    
                    setTestCases(testCases);
                    return;
                } else {
                    console.warn('Bulk endpoint failed, falling back to parallel individual calls');
                }
            } catch (bulkError) {
                console.warn('Bulk endpoint error, falling back to parallel individual calls:', bulkError);
            }
            
            // Fallback: Use parallel individual calls if bulk endpoint fails
            console.log('Using fallback: parallel individual API calls...');
            
            const promises = suiteTypes.map(async (suiteType) => {
                try {
                    const apiUrl = buildApiUrl(`/api/testcases?suite_type=${suiteType}&module_id=${selectedModule.id}`);
                    const response = await fetch(apiUrl);
                    if (response.ok) {
                        const data = await response.json();
                        return {
                            suiteType,
                            testCases: data.test_cases || [],
                            success: true
                        };
                    }
                    return { suiteType, testCases: [], success: false };
                } catch (err) {
                    console.log(`Error with suite_type ${suiteType}:`, err);
                    return { suiteType, testCases: [], success: false };
                }
            });
            
            const results = await Promise.allSettled(promises);
            
            let allTestCases: TestCase[] = [];
            results.forEach((result, index) => {
                if (result.status === 'fulfilled' && result.value.success) {
                    const { suiteType, testCases } = result.value;
                    if (testCases.length > 0) {
                        console.log(`Found ${testCases.length} test cases with suite_type: ${suiteType}`);
                        allTestCases = [...allTestCases, ...testCases];
                    }
                }
            });
            
            // Remove duplicates based on id
            const uniqueTestCases = allTestCases.reduce((unique: TestCase[], testCase: TestCase) => {
                if (!unique.find(tc => tc.id === testCase.id)) {
                    unique.push(testCase);
                }
                return unique;
            }, []);
            
            const endTime = performance.now();
            console.log(`⚡ Parallel fetch: Found ${uniqueTestCases.length} unique test cases in ${(endTime - startTime).toFixed(2)}ms`);
            
            setTestCases(uniqueTestCases);
            
        } catch (error) {
            console.error('Error fetching test cases:', error);
            setTestCases([]);
        } finally {
            setIsLoadingTestCases(false);
        }
    };

    const fetchTestSteps = async (testCase: TestCase) => {
        try {
            setIsLoadingSteps(true); // Prevent auto-save during loading
            const response = await fetch(buildApiUrl(`/api/teststeps/${encodeURIComponent(testCase.name)}`));
            if (response.ok) {
                const steps = await response.json();
                setTestSteps(steps || []);
                setViewingTestCase(testCase);
                setShowTestSteps(true);
                setEditingSteps(false);
            } else {
                // If no test steps exist, still show the view to allow creating them
                setTestSteps([]);
                setViewingTestCase(testCase);
                setShowTestSteps(true);
                setEditingSteps(false);
            }
        } catch (error) {
            console.error('Error fetching test steps:', error);
            setTestSteps([]);
            setViewingTestCase(testCase);
            setShowTestSteps(true);
            setEditingSteps(false);
        } finally {
            setIsLoadingSteps(false); // Allow auto-save after loading
        }
    };

    const saveTestSteps = async () => {
        if (!viewingTestCase) return;

        try {
            const response = await fetch(buildApiUrl(`/api/teststeps/${encodeURIComponent(viewingTestCase.name)}/bulk`), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    id: viewingTestCase.id,
                    clear_existing: true, // overwrite existing steps
                    project_name: viewingTestCase.project_name || viewingTestCase.project,
                    module_name: viewingTestCase.module_name || viewingTestCase.module,
                    steps: testSteps.map((step, idx) => ({
                        // ensure consistent shape for backend
                        tc_id: viewingTestCase.name,
                        step_no: idx + 1,
                        test_step_description: step.test_step_description || '',
                        page: (step as any).page || '',
                        element_name: step.element_name || '',
                        action_type: step.action_type || 'CLICK',
                        xpath: step.xpath || '',
                        values: step.values || ''
                    }))
                })
            });

            if (response.ok) {
                setEditingSteps(false);
                toast({
                    title: "Success",
                    description: "Test steps saved successfully!",
                });
                // Refresh test steps from server
                await fetchTestSteps(viewingTestCase);
            } else {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData?.error || 'Failed to save test steps');
            }
        } catch (error) {
            console.error('Error saving test steps:', error);
            toast({
                title: "Error",
                description: error instanceof Error ? error.message : "Failed to save test steps",
                variant: "destructive"
            });
        }
    };

    const handleCreateTestCase = async () => {
        if (!formData.name.trim()) {
            toast({
                title: "Error",
                description: "Test case name is required",
                variant: "destructive"
            });
            return;
        }

        try {
            const response = await fetch(buildApiUrl('/api/testcases'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    suite_type: 'general',
                    module_id: selectedModule?.id,
                    project_name: selectedProject?.name || selectedProject?.project_name,
                    module_name: selectedModule?.module_name || selectedModule?.name,
                    name: formData.name,
                    description: formData.description,
                    priority: formData.priority,
                    status: 'Active'
                }),
            });

            if (response.ok) {
                const result = await response.json();
                // Refresh the test cases list
                await fetchTestCases();
                setFormData({ name: '', description: '', priority: 'Medium' });
                setIsCreateModalOpen(false);

                toast({
                    title: "Success",
                    description: `Test case "${formData.name}" created successfully!`,
                });
            } else {
                const error = await response.json();
                toast({
                    title: "Error",
                    description: error.error || "Failed to create test case",
                    variant: "destructive"
                });
            }
        } catch (error) {
            console.error('Error creating test case:', error);
            toast({
                title: "Error",
                description: "Failed to connect to backend API",
                variant: "destructive"
            });
        }
    };

    const handleEditTestCase = (testCase: TestCase) => {
        setEditingTestCase(testCase);
        setFormData({
            name: testCase.name,
            description: testCase.description,
            priority: testCase.priority
        });
        setIsEditModalOpen(true);
    };

    const handleUpdateTestCase = async () => {
        if (!editingTestCase || !formData.name.trim()) {
            toast({
                title: "Error",
                description: "Test case name is required",
                variant: "destructive"
            });
            return;
        }

        try {
            const response = await fetch(buildApiUrl(`/api/testcases/${editingTestCase.id}`), {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    name: formData.name,
                    description: formData.description,
                    priority: formData.priority,
                    module_id: editingTestCase.module_id,
                    project_name: selectedProject?.name || selectedProject?.project_name,
                    module_name: selectedModule?.module_name || selectedModule?.name,
                    suite_type: 'general'
                })
            });

            if (response.ok) {
                await fetchTestCases();
                setIsEditModalOpen(false);
                setEditingTestCase(null);
                setFormData({ name: '', description: '', priority: 'Medium' });
                toast({
                    title: "Success",
                    description: "Testcase updated successfully!",
                });
            } else {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to update testcase');
            }
        } catch (error) {
            console.error('Update error:', error);
            toast({
                title: "Error",
                description: error instanceof Error ? error.message : "Failed to update testcase",
                variant: "destructive"
            });
        }
    };

    const handleDeleteTestCase = async (testCase: TestCase) => {
        if (!window.confirm(`Are you sure you want to delete "${testCase.name}"?`)) {
            return;
        }

        try {
            const response = await fetch(buildApiUrl(`/api/testcases/${testCase.id}`), {
                method: 'DELETE'
            });

            if (response.ok) {
                await fetchTestCases();
                toast({
                    title: "Success",
                    description: "Testcase deleted successfully!",
                });
            } else {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to delete testcase');
            }
        } catch (error) {
            console.error('Delete error:', error);
            toast({
                title: "Error",
                description: error instanceof Error ? error.message : "Failed to delete testcase",
                variant: "destructive"
            });
        }
    };

    const handleTestCaseSelect = (testCase: TestCase) => {
        setSelectedTestCase(testCase);
        if (developmentMode) {
            // In development mode, directly show test steps in read-only
            fetchTestSteps(testCase);
        } else {
            onTestCaseSelect(testCase);
        }
    };

    const handleCleanupOrphanedData = async () => {
        if (!window.confirm('This will permanently delete all orphaned test execution data that no longer has corresponding test cases. Are you sure?')) {
            return;
        }

        try {
            const response = await fetch(buildApiUrl('/api/cleanup-orphaned-data'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (response.ok) {
                const result = await response.json();
                toast({
                    title: "Success",
                    description: `Cleanup completed! Deleted ${result.details.total_deleted} orphaned records.`,
                });
                // Refresh test cases to ensure clean state
                await fetchTestCases();
            } else {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to cleanup orphaned data');
            }
        } catch (error) {
            console.error('Cleanup error:', error);
            toast({
                title: "Error",
                description: error instanceof Error ? error.message : "Failed to cleanup orphaned data",
                variant: "destructive"
            });
        }
    };

    const handleGenerateTestcase = async () => {
        if (selectedBrdFiles.length === 0) {
            toast({
                title: "Error",
                description: "Please select at least one BRD document first",
                variant: "destructive"
            });
            return;
        }

        try {
            toast({
                title: "Generating Test Cases",
                description: "Processing BRD documents with AI...",
            });

            const response = await fetch(buildApiUrl('/api/generate-testcases-from-brd'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Email': localStorage.getItem('qfast_user') ? JSON.parse(localStorage.getItem('qfast_user')!).email : '',
                },
                body: JSON.stringify({
                    brd_files: selectedBrdFiles.map(file => ({ id: file.id, name: file.file_name })),
                    project_id: selectedProject?.id,
                    module_id: selectedModule?.id
                })
            });

            if (response.ok) {
                const result = await response.json();
                toast({
                    title: "Success",
                    description: `Generated ${result.generated_testcases.length} test cases from BRD documents!`,
                });

                // Refresh test cases list to show the new ones
                await fetchTestCases();

                // Clear BRD selection
                setSelectedBrdFiles([]);
                setBrdPanelOpen(false);
            } else {
                const errorData = await response.json().catch(() => ({ error: 'Unknown error occurred' }));
                throw new Error(errorData.error || 'Failed to generate test cases');
            }
        } catch (error) {
            console.error('Generate testcase error:', error);

            // Enhanced error handling for different error types
            let errorMessage = "Failed to generate test cases from BRD";

            if (error instanceof Error) {
                // Handle specific error types
                if (error.message.includes('Groq API error')) {
                    errorMessage = "AI service temporarily unavailable. Please try again later.";
                } else if (error.message.includes('JSON')) {
                    errorMessage = "AI response format error. Please try again.";
                } else if (error.message.includes('Authentication')) {
                    errorMessage = "Authentication failed. Please check your login.";
                } else if (error.message.includes('No BRD files selected')) {
                    errorMessage = "Please select at least one BRD document first.";
                } else if (error.message.includes('No readable content')) {
                    errorMessage = "Selected BRD files contain no readable content.";
                } else {
                    errorMessage = error.message;
                }
            }

            toast({
                title: "Error",
                description: errorMessage,
                variant: "destructive"
            });
        }
    };

    const handleProceed = () => {
        if (!selectedTestCase) {
            toast({
                title: "Error",
                description: "Please select a test case to proceed",
                variant: "destructive"
            });
            return;
        }
        onNext();
    };

    // BRD Functions
    const loadBrdFiles = async () => {
        try {
            const response = await fetch(buildApiUrl('/api/brd/files'), {
                method: 'GET',
                headers: {
                    'X-User-Email': localStorage.getItem('qfast_user') ? JSON.parse(localStorage.getItem('qfast_user')!).email : '',
                },
            });

            if (response.ok) {
                const result = await response.json();
                setBrdFiles(result.files || []);
            }
        } catch (error) {
            console.error('Error loading BRD files:', error);
        }
    };

    const handleBrdDownload = async (fileId: number, fileName: string) => {
        try {
            const response = await fetch(buildApiUrl(`/api/brd/download/${fileId}`), {
                method: 'GET',
                headers: {
                    'X-User-Email': localStorage.getItem('qfast_user') ? JSON.parse(localStorage.getItem('qfast_user')!).email : '',
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
            }
        } catch (error) {
            console.error('Error downloading BRD file:', error);
        }
    };

    const handleBrdFileSelect = (file: any) => {
        setSelectedBrdFiles(prev => {
            const isSelected = prev.some(f => f.id === file.id);
            if (isSelected) {
                return prev.filter(f => f.id !== file.id);
            } else {
                return [...prev, file];
            }
        });
    };

    const formatFileSize = (bytes: number) => {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const filteredBrdFiles = brdFiles.filter(file => {
        const matchesSearch = file.file_name.toLowerCase().includes(brdSearchTerm.toLowerCase()) ||
                             file.original_name.toLowerCase().includes(brdSearchTerm.toLowerCase());
        const matchesType = brdFilterType === 'all' || file.file_type === brdFilterType;
        return matchesSearch && matchesType;
    });

    const getPriorityColor = (priority: string) => {
        switch (priority.toLowerCase()) {
            case 'high': return 'bg-red-500/20 text-red-600';
            case 'medium': return 'bg-yellow-500/20 text-yellow-600';
            case 'low': return 'bg-green-500/20 text-green-600';
            default: return 'bg-gray-500/20 text-gray-600';
        }
    };

    const renderTestStepsView = () => (
        <div className="space-y-6">
            {/* Header */}
            <Card className="bg-white backdrop-blur-sm border-gray-200">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="text-2xl text-gray-900 flex items-center space-x-2">
                                <List className="w-6 h-6 text-purple-600" />
                                <span>Test Steps - {viewingTestCase?.name}</span>
                            </CardTitle>
                            <p className="text-gray-600 mt-2">
                                {developmentMode 
                                    ? '📖 Read-Only Mode: Test steps cannot be edited in development mode' 
                                    : editingSteps 
                                        ? 'Edit and manage test steps with full CRUD operations' 
                                        : 'View test step details for this test case'
                                }
                            </p>
                            {developmentMode && (
                                <div className="mt-2 p-3 bg-orange-50 border border-orange-200 rounded-lg">
                                    <p className="text-orange-700 text-sm">
                                        <strong>Development Mode:</strong> Test case and steps are read-only. 
                                        Use the main development workflow to create and manage test steps.
                                    </p>
                                </div>
                            )}
                        </div>
                        <div className="flex space-x-2">
                            {editingSteps ? (
                                <>
                                    <Button
                                        onClick={saveTestSteps}
                                        className="bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600"
                                    >
                                        <Save className="w-4 h-4 mr-2" />
                                        Save Changes
                                    </Button>
                                    <Button
                                        variant="outline"
                                        onClick={() => setEditingSteps(false)}
                                        className="border-gray-300 text-gray-600"
                                    >
                                        Cancel
                                    </Button>
                                </>
                            ) : (
                                !developmentMode && (
                                    <Button
                                        onClick={() => setEditingSteps(true)}
                                        className="bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-600 hover:to-indigo-600"
                                    >
                                        <Edit className="w-4 h-4 mr-2" />
                                        Edit Steps
                                    </Button>
                                )
                            )}
                            <Button
                                variant="outline"
                                onClick={() => setShowTestSteps(false)}
                                className="border-gray-200 text-gray-600"
                            >
                                <ArrowLeft className="w-4 h-4 mr-2" />
                                Back to Test Cases
                            </Button>
                        </div>
                    </div>
                </CardHeader>
            </Card>

            {/* Test Steps Content */}
            {editingSteps && !developmentMode ? (
                <>
                    {/* Add New Step Button */}
                    <div className="flex justify-end">
                        <Button
                            onClick={() => testStepsGridRef.current?.addNewStep()}
                            className="bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600"
                        >
                            <Plus className="w-4 h-4 mr-2" />
                            Add New Step
                        </Button>
                    </div>

                    {/* Editable Test Steps Grid */}
                    <TestStepsGrid
                        ref={testStepsGridRef}
                        selectedProject={selectedProject}
                        selectedModule={selectedModule}
                        testSteps={testSteps}
                        testCaseName={viewingTestCase?.name}
                        onTestStepsChange={(steps) => {
                            // Update local state immediately
                            setTestSteps(steps);

                            // Skip auto-save if steps are currently being loaded from database
                            if (isLoadingSteps) {
                                console.log('⏭️ [Auto-Save Skipped] Steps are being loaded from database');
                                return;
                            }

                            // Debounced auto-save to prevent race conditions
                            if (!viewingTestCase) return;

                            // Clear any existing timeout
                            if (window.testStepsAutoSaveTimeout) {
                                clearTimeout(window.testStepsAutoSaveTimeout);
                            }

                            // Set a new timeout for auto-save (500ms delay)
                            window.testStepsAutoSaveTimeout = setTimeout(async () => {
                                try {
                                    console.log('💾 [Auto-Save] Saving test steps to database...');
                                    const response = await fetch(buildApiUrl(`/api/teststeps/${encodeURIComponent(viewingTestCase.name)}/bulk`), {
                                        method: 'POST',
                                        headers: {
                                            'Content-Type': 'application/json',
                                        },
                                        body: JSON.stringify({
                                            id: viewingTestCase.id,
                                            clear_existing: true,
                                            project_name: viewingTestCase.project_name || viewingTestCase.project,
                                            module_name: viewingTestCase.module_name || viewingTestCase.module,
                                            steps: steps.map((step, idx) => ({
                                                tc_id: viewingTestCase.name,
                                                step_no: idx + 1,
                                                test_step_description: step.test_step_description || '',
                                                page: (step as any).page || '',
                                                element_name: step.element_name || '',
                                                action_type: step.action_type || 'CLICK',
                                                xpath: step.xpath || '',
                                                values: step.values || ''
                                            }))
                                        })
                                    });

                                    if (response.ok) {
                                        console.log('💾 [Auto-Save Success] Test steps auto-saved to database');
                                    } else {
                                        const errorData = await response.json().catch(() => ({}));
                                        console.error('❌ [Auto-Save Failed]', errorData?.error || 'Failed to auto-save test steps');
                                    }
                                } catch (error) {
                                    console.error('❌ [Auto-Save Error]', error);
                                }
                            }, 500);
                        }}
                        readOnlyMode={developmentMode}
                        onAutoXPathRefresh={async (steps) => {
                            // Skip auto-save if steps are currently being loaded from database
                            if (isLoadingSteps) {
                                console.log('⏭️ [XPath Auto-Save Skipped] Steps are being loaded from database');
                                return;
                            }

                            // Create a temporary state update for saving
                            const stepsToBeSaved = steps;
                            if (!viewingTestCase) return;

                            try {
                                const response = await fetch(buildApiUrl(`/api/teststeps/${encodeURIComponent(viewingTestCase.name)}/bulk`), {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                    },
                                    body: JSON.stringify({
                                        id: viewingTestCase.id,
                                        clear_existing: true,
                                        project_name: viewingTestCase.project_name || viewingTestCase.project,
                                        module_name: viewingTestCase.module_name || viewingTestCase.module,
                                        steps: stepsToBeSaved.map((step, idx) => ({
                                            tc_id: viewingTestCase.name,
                                            step_no: idx + 1,
                                            test_step_description: step.test_step_description || '',
                                            page: (step as any).page || '',
                                            element_name: step.element_name || '',
                                            action_type: step.action_type || 'CLICK',
                                            xpath: step.xpath || '',
                                            values: step.values || ''
                                        }))
                                    })
                                });

                                if (response.ok) {
                                    console.log('💾 [Auto-Save Success] XPath changes auto-saved to database');
                                } else {
                                    const errorData = await response.json().catch(() => ({}));
                                    console.error('❌ [Auto-Save Failed]', errorData?.error || 'Failed to auto-save XPath changes');
                                }
                            } catch (error) {
                                console.error('❌ [Auto-Save Error]', error);
                            }
                        }}
                    />
                </>
            ) : (
                /* Read-only Test Steps View */
                <Card className="bg-white backdrop-blur-sm border-gray-200">
                    <CardHeader>
                        <CardTitle className="text-lg text-gray-900">Test Steps ({testSteps.length})</CardTitle>
                    </CardHeader>
                    <CardContent>
                        {testSteps.length === 0 ? (
                            <div className="text-center py-8">
                                <List className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                                <p className="text-gray-600">
                                    {developmentMode 
                                        ? "No test steps found for this test case. Test steps are read-only in development mode." 
                                        : "No test steps found for this test case"
                                    }
                                </p>
                                {!developmentMode && (
                                    <Button
                                        onClick={() => setEditingSteps(true)}
                                        className="mt-4 bg-gradient-to-r from-blue-500 to-indigo-500"
                                    >
                                        <Plus className="w-4 h-4 mr-2" />
                                        Add First Step
                                    </Button>
                                )}
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {testSteps.map((step, index) => (
                                    <Card key={step.id} className="border border-gray-200">
                                        <CardContent className="p-4">
                                            <div className="flex items-start space-x-4">
                                                <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white text-sm font-bold">
                                                    {step.step_no}
                                                </div>
                                                <div className="flex-1 space-y-2">
                                                    <span className="font-medium text-gray-700">Description:</span>
                                                    <h4 className="font-semibold text-gray-900">{step.test_step_description}</h4>
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                                                        <div>
                                                            <span className="font-medium text-gray-700">Element:</span>
                                                            <p className="text-gray-600">{step.element_name || 'N/A'}</p>
                                                        </div>
                                                        <div>
                                                            <span className="font-medium text-gray-700">Page:</span>
                                                            <p className="text-gray-600">{step.page|| 'N/A'}</p>
                                                        </div>
                                                        <div>

                                                            <span className="font-medium text-gray-700">Action:</span>
                                                            <p className="text-gray-600">{step.action_type || 'N/A'}</p>
                                                        </div>
                                                        <div>
                                                            <span className="font-medium text-gray-700">XPath:</span>
                                                            <p className="text-gray-600 font-mono text-xs break-all">{step.xpath || 'N/A'}</p>
                                                        </div>
                                                        <div>
                                                            <span className="font-medium text-gray-700">Values:</span>
                                                            <p className="text-gray-600">{step.values || 'N/A'}</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </CardContent>
                </Card>
            )}
        </div>
    );

    if (!selectedModule) {
        return (
            <Card className="bg-white backdrop-blur-sm border-gray-200">
                <CardContent className="p-8 text-center">
                    <p className="text-gray-600">Please select a module first</p>
                </CardContent>
            </Card>
        );
    }

    if (showTestSteps) {
        return renderTestStepsView();
    }

    return (
        <div className="space-y-6">
            {/* Header Section */}
            <Card className="bg-white backdrop-blur-sm border-gray-200">
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            {developmentMode ? (
                                <h3 className="font-semibold tracking-tight text-lg text-gray-900">Test Cases</h3>
                            ) : (
                                <CardTitle className="text-2xl text-gray-900 flex items-center space-x-2">
                                    <TestTube className="w-6 h-6 text-blue-600" />
                                    <span>Test Cases - {selectedModule?.module_name || selectedModule?.name}</span>
                                </CardTitle>
                            )}
                            <p className="text-gray-600 mt-2">Manage test cases from Automation Planning, Development, and Execution phases</p>
                        </div>
                        {!developmentMode && (
                            <div className="flex space-x-2">
                                <Sheet open={brdPanelOpen} onOpenChange={setBrdPanelOpen}>
                                    <SheetTrigger asChild>
                                        <Button
                                            variant="outline"
                                            className="border-blue-200 text-blue-600 hover:bg-blue-50"
                                            onClick={() => {
                                                loadBrdFiles();
                                                setBrdPanelOpen(true);
                                            }}
                                        >
                                            <FileText className="w-4 h-4 mr-2" />
                                            Select Document
                                        </Button>
                                    </SheetTrigger>
                                    <SheetContent className="w-[400px] sm:w-[540px] bg-white">
                                        <SheetHeader>
                                            <SheetTitle className="text-gray-900">Select BRD Documents</SheetTitle>
                                            <p className="text-sm text-gray-600">Choose BRD documents to associate with your test cases</p>
                                        </SheetHeader>

                                        {/* Search and Filter */}
                                        <div className="mt-6 space-y-4">
                                            <div className="relative">
                                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                                                <Input
                                                    placeholder="Search BRD files..."
                                                    value={brdSearchTerm}
                                                    onChange={(e) => setBrdSearchTerm(e.target.value)}
                                                    className="pl-10 bg-gray-50 border-gray-200"
                                                />
                                            </div>

                                            <div className="flex items-center space-x-2">
                                                <Filter className="w-4 h-4 text-gray-400" />
                                                <select
                                                    value={brdFilterType}
                                                    onChange={(e) => setBrdFilterType(e.target.value)}
                                                    className="flex-1 bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-sm text-gray-900"
                                                >
                                                    <option value="all">All Formats</option>
                                                    <option value="document">Documents (.doc, .docx)</option>
                                                    <option value="pdf">PDF Files</option>
                                                    <option value="excel">Excel Files</option>
                                                </select>
                                            </div>
                                        </div>

                                        {/* Selected Files Summary */}
                                        {selectedBrdFiles.length > 0 && (
                                            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-sm font-medium text-blue-900">
                                                        {selectedBrdFiles.length} file{selectedBrdFiles.length !== 1 ? 's' : ''} selected
                                                    </span>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => setSelectedBrdFiles([])}
                                                        className="text-blue-600 hover:text-blue-800"
                                                    >
                                                        <X className="w-4 h-4" />
                                                    </Button>
                                                </div>
                                            </div>
                                        )}

                                        {/* BRD Files List */}
                                        <div className="mt-6 space-y-3 max-h-[400px] overflow-y-auto">
                                            {filteredBrdFiles.length === 0 ? (
                                                <div className="text-center py-8">
                                                    <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                                                    <p className="text-gray-600">
                                                        {brdFiles.length === 0 ? 'No BRD files uploaded yet' : 'No files match your search'}
                                                    </p>
                                                </div>
                                            ) : (
                                                filteredBrdFiles.map((file) => (
                                                    <div
                                                        key={file.id}
                                                        className={`
                                                            flex items-center justify-between p-3 border rounded-lg cursor-pointer transition-all
                                                            ${selectedBrdFiles.some(f => f.id === file.id)
                                                                ? 'bg-blue-50 border-blue-300'
                                                                : 'bg-gray-50 border-gray-200 hover:bg-gray-100'
                                                            }
                                                        `}
                                                        onClick={() => handleBrdFileSelect(file)}
                                                    >
                                                        <div className="flex items-center space-x-3 flex-1">
                                                            <div className={`
                                                                w-8 h-8 rounded-full flex items-center justify-center
                                                                ${file.file_type === 'document' ? 'bg-blue-100 text-blue-600' :
                                                                  file.file_type === 'pdf' ? 'bg-red-100 text-red-600' :
                                                                  'bg-green-100 text-green-600'}
                                                            `}>
                                                                <FileText className="w-4 h-4" />
                                                            </div>
                                                            <div className="flex-1 min-w-0">
                                                                <p className="font-medium text-gray-900 truncate">{file.file_name}</p>
                                                                <p className="text-sm text-gray-600 truncate">{file.original_name}</p>
                                                                <div className="flex items-center space-x-2 mt-1">
                                                                    <span className="text-xs text-gray-500 uppercase">{file.file_type}</span>
                                                                    <span className="text-xs text-gray-500">{formatFileSize(file.file_size)}</span>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center space-x-2">
                                                            <Button
                                                                variant="ghost"
                                                                size="sm"
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    handleBrdDownload(file.id, file.original_name);
                                                                }}
                                                                className="text-gray-600 hover:text-gray-900"
                                                            >
                                                                <Download className="w-4 h-4" />
                                                            </Button>
                                                            {selectedBrdFiles.some(f => f.id === file.id) && (
                                                                <div className="w-5 h-5 bg-blue-600 rounded-full flex items-center justify-center">
                                                                    <div className="w-2 h-2 bg-white rounded-full"></div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))
                                            )}
                                        </div>

                                        {/* Action Buttons */}
                                        <div className="mt-6 flex justify-end space-x-2">
                                            <Button variant="outline" onClick={() => setBrdPanelOpen(false)}>
                                                Cancel
                                            </Button>
                                            <Button
                                                onClick={() => {
                                                    // Here you can handle what to do with selected BRD files
                                                    toast({
                                                        title: "BRD Selection",
                                                        description: `Selected ${selectedBrdFiles.length} BRD file${selectedBrdFiles.length !== 1 ? 's' : ''}`,
                                                    });
                                                    setBrdPanelOpen(false);
                                                }}
                                                className="bg-blue-600 hover:bg-blue-700"
                                            >
                                                Select Files ({selectedBrdFiles.length})
                                            </Button>
                                        </div>
                                    </SheetContent>
                                </Sheet>
                                <Button
                                    onClick={handleGenerateTestcase}
                                    disabled={selectedBrdFiles.length === 0}
                                    className="bg-gradient-to-r from-purple-500 to-indigo-500 hover:from-purple-600 hover:to-indigo-600 disabled:opacity-50"
                                >
                                    <TestTube className="w-4 h-4 mr-2" />
                                    Generate Testcase
                                </Button>
                            </div>
                        )}
                        {!developmentMode && (
                            <div className="flex space-x-2">
                                <Button
                                    onClick={handleCleanupOrphanedData}
                                    variant="outline"
                                    className="border-red-200 text-red-600 hover:bg-red-50"
                                >
                                    <Database className="w-4 h-4 mr-2" />
                                    Cleanup Database
                                </Button>
                                <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
                                <DialogTrigger asChild>
                                    <Button className="bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-600 hover:to-indigo-600">
                                        <Plus className="w-4 h-4 mr-2" />
                                        Create Test Case
                                    </Button>
                                </DialogTrigger>
                                <DialogContent className="bg-white border-gray-200">
                                    <DialogHeader>
                                        <DialogTitle className="text-gray-900">Create New Test Case</DialogTitle>
                                    </DialogHeader>
                                    <div className="space-y-4">
                                        <div>
                                            <label className="text-sm font-medium text-gray-600">Test Case Name</label>
                                            <Input
                                                value={formData.name}
                                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                                placeholder="Enter test case name"
                                                className="bg-gray-50 border-gray-200 text-gray-900"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-sm font-medium text-gray-600">Description</label>
                                            <Textarea
                                                value={formData.description}
                                                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                                placeholder="Enter test case description"
                                                className="bg-gray-50 border-gray-200 text-gray-900"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-sm font-medium text-gray-600">Priority</label>
                                            <select
                                                value={formData.priority}
                                                onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                                                className="w-full bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-gray-900"
                                            >
                                                <option value="High">High</option>
                                                <option value="Medium">Medium</option>
                                                <option value="Low">Low</option>
                                            </select>
                                        </div>
                                        <div className="flex justify-end space-x-2">
                                            <Button variant="outline" onClick={() => setIsCreateModalOpen(false)}>
                                                Cancel
                                            </Button>
                                            <Button onClick={handleCreateTestCase} className="bg-gradient-to-r from-blue-500 to-indigo-500">
                                                Create TestCase
                                            </Button>
                                        </div>
                                    </div>
                                </DialogContent>
                            </Dialog>

                            {/* Edit Test Case Modal */}
                            <Dialog open={isEditModalOpen} onOpenChange={setIsEditModalOpen}>
                                <DialogContent className="bg-white border-gray-200">
                                    <DialogHeader>
                                        <DialogTitle className="text-gray-900">Edit Test Case</DialogTitle>
                                    </DialogHeader>
                                    <div className="space-y-4">
                                        <div>
                                            <label className="text-sm font-medium text-gray-600">Test Case Name</label>
                                            <Input
                                                value={formData.name}
                                                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                                placeholder="Enter test case name"
                                                className="bg-gray-50 border-gray-200 text-gray-900"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-sm font-medium text-gray-600">Description</label>
                                            <Textarea
                                                value={formData.description}
                                                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                                placeholder="Enter test case description"
                                                className="bg-gray-50 border-gray-200 text-gray-900"
                                            />
                                        </div>
                                        <div>
                                            <label className="text-sm font-medium text-gray-600">Priority</label>
                                            <select
                                                value={formData.priority}
                                                onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                                                className="w-full bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-gray-900"
                                            >
                                                <option value="High">High</option>
                                                <option value="Medium">Medium</option>
                                                <option value="Low">Low</option>
                                            </select>
                                        </div>
                                        <div className="flex justify-end space-x-2">
                                            <Button variant="outline" onClick={() => setIsEditModalOpen(false)}>
                                                Cancel
                                            </Button>
                                            <Button onClick={handleUpdateTestCase} className="bg-gradient-to-r from-blue-500 to-indigo-500">
                                                Update TestCase
                                            </Button>
                                        </div>
                                    </div>
                                </DialogContent>
                            </Dialog>
                            </div>
                        )}
                    </div>
                </CardHeader>
            </Card>

            {/* Database Info */}
            <Card className="bg-blue-500/10 backdrop-blur-sm border-blue-500/20">
                <CardContent className="p-4">
                    <div className="flex items-center space-x-2 text-blue-600">
                        <Database className="w-4 h-4" />
                        <span className="text-sm">Database: Ixigo_TestAutomation | Server: LPT2084-B1</span>
                    </div>
                </CardContent>
            </Card>

            {/* Test Cases Grid */}
            {isLoadingTestCases ? (
                <div className="text-center py-12">
                    <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4 animate-spin">
                        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
                    </div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">Loading Test Cases...</h3>
                    <p className="text-gray-500 mb-4">
                        Fetching test cases from all suite types using optimized bulk query
                    </p>
                </div>
            ) : testCases.length === 0 ? (
                <div className="text-center py-12">
                    <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                        <TestTube className="w-8 h-8 text-gray-400" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-700 mb-2">No Test Cases</h3>
                    <p className="text-gray-500 mb-4">
                        {readOnlyMode 
                            ? "No test cases are available for this module."
                            : "Start by creating your first test case using the button above"
                        }
                    </p>
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full border-collapse border border-gray-200">
                        <thead>
                            <tr className="bg-gray-50">
                                <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 min-w-[200px]">
                                    Test Case Name
                                </th>
                                <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 min-w-[300px]">
                                    Description
                                </th>
                                <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-40">
                                    Test Case ID
                                </th>
                                <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-24">
                                    Priority
                                </th>
                                <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-24">
                                    Status
                                </th>
                                <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-32">
                                    Created Date
                                </th>
                                <th className="border border-gray-200 px-4 py-3 text-center text-sm font-medium text-gray-700 w-40">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {testCases.map((testCase) => (
                                <tr 
                                    key={testCase.id}
                                    className={`
                                        cursor-pointer transition-all duration-200 hover:bg-gray-50
                                        ${selectedTestCase?.id === testCase.id
                                            ? 'bg-blue-50 border-blue-200'
                                            : highlightTestCase === testCase.name
                                            ? 'bg-green-50 border-green-200'
                                            : 'hover:bg-gray-50'
                                        }
                                    `}
                                    onClick={() => handleTestCaseSelect(testCase)}
                                >
                                    {/* Test Case Name */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        <div className="flex items-center space-x-2">
                                            <span className="font-medium text-gray-900">{testCase.name}</span>
                                            {highlightTestCase === testCase.name && (
                                                <Badge className="bg-green-500 text-white animate-pulse text-xs">
                                                    ✨ Recently Synced
                                                </Badge>
                                            )}
                                        </div>
                                    </td>

                                    {/* Description */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        <p className="text-gray-600 text-sm">{testCase.description}</p>
                                    </td>

                                    {/* Test Case ID */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        {testCase.testcase_id && (
                                            <span className="font-mono text-xs text-blue-900 bg-blue-50 px-2 py-1 rounded">
                                                {testCase.testcase_id}
                                            </span>
                                        )}
                                    </td>

                                    {/* Priority */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        <Badge className={getPriorityColor(testCase.priority)}>
                                            {testCase.priority}
                                        </Badge>
                                    </td>

                                    {/* Status */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        <Badge variant="secondary" className="bg-green-500/20 text-green-600">
                                            {testCase.status}
                                        </Badge>
                                    </td>

                                    {/* Created Date */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        <span className="text-xs text-gray-600">
                                            {formatExecutionDate(testCase.created_date, { includeTime: false })}
                                        </span>
                                    </td>

                                    {/* Actions */}
                                    <td className="border border-gray-200 px-4 py-3">
                                        {!developmentMode && (
                                            <div className="flex items-center justify-center space-x-1">
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="text-blue-600 hover:text-blue-800 h-8 w-8 p-0"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        fetchTestSteps(testCase);
                                                    }}
                                                    title="View Test Steps"
                                                >
                                                    <Eye className="w-4 h-4" />
                                                </Button>
                                                {!readOnlyMode && (
                                                    <>
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="text-gray-600 hover:text-gray-900 h-8 w-8 p-0"
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                handleEditTestCase(testCase);
                                                            }}
                                                            title="Edit Test Case"
                                                        >
                                                            <Edit className="w-4 h-4" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            className="text-red-600 hover:text-red-800 h-8 w-8 p-0"
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                handleDeleteTestCase(testCase);
                                                            }}
                                                            title="Delete Test Case"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </Button>
                                                    </>
                                                )}
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Navigation */}
            {!developmentMode && (
                <div className="flex justify-between items-center">
                    <Button variant="outline" onClick={onBack} className="border-gray-200 text-gray-600">
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Back to Modules
                    </Button>
                </div>
            )}

            {/* Development Mode Navigation */}
            {developmentMode && (
                <div className="flex justify-between items-center">
                    <Button variant="outline" onClick={onBack} className="border-gray-200 text-gray-600">
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Back to Modules
                    </Button>
                </div>
            )}
        </div>
    );
};

export default TestCaseDashboard;


