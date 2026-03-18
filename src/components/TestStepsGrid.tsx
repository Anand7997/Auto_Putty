import React, { useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Edit, Trash2, ArrowUp, ArrowDown, PlusCircle, Save, X, RefreshCw, CheckCircle, Copy, FileSpreadsheet, Database } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { buildApiUrl } from '@/config/api';
import useAutoXPathRefresh from '@/hooks/useAutoXPathRefresh';
import ExcelUploadSidebar from './ExcelUploadSidebar';


// Chrome extension type declarations
declare global {
  interface Window {
    chrome: any;
    debugTestSteps?: (steps: any[], source?: string) => void;
  }
}

interface TestStep {
  id: number;
  tc_id: string;
  step_no: number;
  test_step_description: string;
  page?: string; // New: associated page name
  element_name: string;
  action_type: string;
  xpath: string;
  values: string;
}

interface TestStepsGridProps {
  selectedProject?: any;
  selectedModule?: any;
  testSteps: TestStep[];
  onTestStepsChange: (steps: TestStep[]) => void;
  readOnlyMode?: boolean;
  onAutoXPathRefresh?: (steps: TestStep[]) => Promise<void>;
  testCaseName?: string;
}

export interface TestStepsGridRef {
  addNewStep: () => void;
  editStep: (stepId: number) => void;
  triggerXPathRefresh: (change?: {
    old_object_name?: string;
    object_name?: string;
    xpath?: string;
    page_name?: string;
  }) => void;
}

const ACTION_TYPES = [
  'OPEN_BROWSER',
  'CLICK',
  'DOUBLE_CLICK',
  'RIGHT_CLICK',
  'MOUSE_OVER',
  'CLICK_AND_SELECT',
  'CLICK_AND_TYPE',
  'CLEAR_AND_TYPE',
  'RADIO_BUTTON',
  'DRAG_AND_DROP',
  'SELECT_COUNT',
  'INCREMENT',
  'DECREMENT',
  'HANDLE_CHECKBOX',
  'SWITCH_TO_NEW_WINDOW',
  'SWITCH_TO_WINDOW_BY_INDEX',
  'SWITCH_TO_WINDOW_BY_URL',
  'SWITCH_TO_IFRAME',
  'CLOSE_EXTRA_WINDOWS',
  'NAVIGATE_TO_URL',
  'REFRESH_PAGE',
  'GO_BACK',
  'GO_FORWARD',
  'TYPE',
  'SELECT',
  'WAIT',
  'PRESS_KEY'
];

const LEGACY_TO_CURRENT_ACTION: Record<string, string> = {
  CLICK_AND_SELECT_DATE: 'CLICK_AND_SELECT',
  CLICK_QUICK_DATE: 'CLICK_AND_SELECT',
  CLICK_BUS_QUICK_DATE: 'CLICK_AND_SELECT',
  CLICK_AND_SELECT_AGE: 'CLICK_AND_SELECT',
  DOUBLECLICK: 'DOUBLE_CLICK',
  RIGHTCLICK: 'RIGHT_CLICK',
  MOUSEOVER: 'MOUSE_OVER',
  MOUSE_HOVER: 'MOUSE_OVER',
  HOVER: 'MOUSE_OVER',
  HOVER_MOUSE_OVER: 'MOUSE_OVER',
  CLEAR_TYPE: 'CLEAR_AND_TYPE',
  TYPE_AND_CLEAR: 'CLEAR_AND_TYPE',
  RADIO: 'RADIO_BUTTON',
  RADIOBUTTON: 'RADIO_BUTTON',
  HANDLE_RADIO: 'RADIO_BUTTON',
  DRAGDROP: 'DRAG_AND_DROP',
  'DRAG_&_DROP': 'DRAG_AND_DROP',
  SWITCH_FRAME: 'SWITCH_TO_IFRAME',
  SWITCH_TO_FRAME: 'SWITCH_TO_IFRAME',
  SWITCH_IFRAME: 'SWITCH_TO_IFRAME',
};

const normalizeActionType = (actionType?: string): string => {
  const raw = (actionType || 'CLICK').toUpperCase().trim().replace(/[\s\-/]+/g, '_');
  if (raw in LEGACY_TO_CURRENT_ACTION) return LEGACY_TO_CURRENT_ACTION[raw];
  if (ACTION_TYPES.includes(raw)) return raw;
  return 'CLICK';
};

const TestStepsGrid = forwardRef<TestStepsGridRef, TestStepsGridProps>(({ 
  selectedProject,
  selectedModule,
  testSteps,
  onTestStepsChange,
  readOnlyMode = false,
  onAutoXPathRefresh,
  testCaseName
}, ref) => {
  const [isAddingNewStep, setIsAddingNewStep] = useState(false);
  const [newStepData, setNewStepData] = useState({
    test_step_description: '',
    page: '',
    element_name: '',
    action_type: 'CLICK',
    xpath: '',
    values: ''
  });
  const [isExcelSidebarOpen, setIsExcelSidebarOpen] = useState(false);
  const [mappedExcelSheet, setMappedExcelSheet] = useState<string>('');
  const [mappedExcelFileId, setMappedExcelFileId] = useState<number | null>(null);
  const [availableMappedSheets, setAvailableMappedSheets] = useState<string[]>([]);
  const [isUpdatingMappedSheet, setIsUpdatingMappedSheet] = useState(false);
  const { toast } = useToast();

  // COMPREHENSIVE DEBUGGING SOLUTION - Step 2: Track Dummy XPath Source
  useEffect(() => {
    console.log('🔍 TESTSTEPS DEBUG: Component mounted');
    console.log('🔍 TESTSTEPS DEBUG: Initial testSteps:', testSteps);
    console.log('🔍 TESTSTEPS DEBUG: onTestStepsChange function available:', typeof onTestStepsChange);
    
    // Override onTestStepsChange to track all changes
    const originalOnTestStepsChange = onTestStepsChange;
    window.debugTestSteps = (steps: TestStep[], source: string = 'unknown') => {
      console.log('🔍 TESTSTEPS DEBUG: New steps from:', source, steps);
      originalOnTestStepsChange(steps);
    };
    
  }, []);

  const applyObjectRenameAndXPathUpdate = (change?: {
    old_object_name?: string;
    object_name?: string;
    xpath?: string;
    page_name?: string;
  }) => {
    if (!change) return;

    const oldName = String(change.old_object_name || '').trim();
    const newName = String(change.object_name || '').trim();
    const newXPath = String(change.xpath || '').trim();
    const changedPage = String(change.page_name || '').trim();

    if (!newName && !newXPath) return;

    const updatedSteps = testSteps.map(step => {
      const stepPage = String(step.page || '').trim();
      const pageMatches = !changedPage || !stepPage || stepPage === changedPage;
      const nameMatches =
        (oldName && step.element_name === oldName) ||
        (!oldName && newName && step.element_name === newName);

      if (!pageMatches || !nameMatches) {
        return step;
      }

      const nextStep = { ...step };
      if (newName && nextStep.element_name !== newName) {
        nextStep.element_name = newName;
      }
      if (newXPath && nextStep.xpath !== newXPath) {
        nextStep.xpath = newXPath;
      }
      return nextStep;
    });

    const hasChanges = updatedSteps.some((step, idx) =>
      step.element_name !== testSteps[idx].element_name || step.xpath !== testSteps[idx].xpath
    );

    if (!hasChanges) return;

    onTestStepsChange(updatedSteps);

    if (onAutoXPathRefresh) {
      onAutoXPathRefresh(updatedSteps).catch(error => {
        console.error('❌ [Object Rename Sync] Failed to save updated steps:', error);
      });
    }
  };

  useImperativeHandle(ref, () => ({
    addNewStep: handleAddNewStep,
    editStep: () => {}, // Not needed anymore
    triggerXPathRefresh: (change) => {
      applyObjectRenameAndXPathUpdate(change);
      triggerRefresh();
    },
  }));

  const updateStep = (stepId: number, field: keyof TestStep, value: string | number) => {
    console.log('updateStep called:', { stepId, field, value });
    const updatedSteps = testSteps.map(step => {
      if (step.id === stepId) {
        const updatedValue = field === 'action_type' ? normalizeActionType(String(value)) : value;
        const updated = { ...step, [field]: updatedValue };
        
        // If page is changed, clear element_name and xpath to avoid confusion
        if (field === 'page') {
          updated.element_name = '';
          updated.xpath = '';
        }
        
        console.log('updateStep - updated step:', updated);
        return updated;
      }
      return step;
    });
    console.log('updateStep - calling onTestStepsChange with:', updatedSteps);
    onTestStepsChange(updatedSteps);
  };

  // New function to update multiple fields at once
  const updateStepMultiple = (stepId: number, updates: Partial<TestStep>) => {
    console.log('updateStepMultiple called:', { stepId, updates });
    const updatedSteps = testSteps.map(step => {
      if (step.id === stepId) {
        const updated = { ...step, ...updates };
        console.log('updateStepMultiple - updated step:', updated);
        return updated;
      }
      return step;
    });
    console.log('updateStepMultiple - calling onTestStepsChange with:', updatedSteps);
    onTestStepsChange(updatedSteps);
  };

  const deleteStep = (stepId: number) => {
    const updatedSteps = testSteps.filter(step => step.id !== stepId);
    // Reorder step numbers
    const reorderedSteps = updatedSteps.map((step, index) => ({
      ...step,
      step_no: index + 1
    }));
    onTestStepsChange(reorderedSteps);
    toast({
      title: "Step Deleted",
      description: "Test step has been removed successfully",
    });
  };

  const moveStepUp = (index: number) => {
    if (index === 0) return;
    
    const updatedSteps = [...testSteps];
    [updatedSteps[index - 1], updatedSteps[index]] = [updatedSteps[index], updatedSteps[index - 1]];
    
    // Reorder step numbers
    const reorderedSteps = updatedSteps.map((step, idx) => ({
      ...step,
      step_no: idx + 1
    }));
    
    onTestStepsChange(reorderedSteps);
  };

  const moveStepDown = (index: number) => {
    if (index === testSteps.length - 1) return;
    
    const updatedSteps = [...testSteps];
    [updatedSteps[index], updatedSteps[index + 1]] = [updatedSteps[index + 1], updatedSteps[index]];
    
    // Reorder step numbers
    const reorderedSteps = updatedSteps.map((step, idx) => ({
      ...step,
      step_no: idx + 1
    }));
    
    onTestStepsChange(reorderedSteps);
  };

  const insertStepAfter = (afterIndex: number) => {
    const newStep: TestStep = {
      id: Date.now() + Math.random(),
      tc_id: 'TC001',
      step_no: afterIndex + 2,
      test_step_description: '',
      page: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    };
    
    const updatedSteps = [...testSteps];
    updatedSteps.splice(afterIndex + 1, 0, newStep);
    
    // Reorder step numbers
    const reorderedSteps = updatedSteps.map((step, index) => ({
      ...step,
      step_no: index + 1
    }));
    
    onTestStepsChange(reorderedSteps);
  };



  const handleAddNewStep = () => {
    if (readOnlyMode) {
      toast({
        title: "Read-Only Mode",
        description: "Cannot add steps in read-only mode",
        variant: "destructive"
      });
      return;
    }
    
    if (isAddingNewStep) {
      toast({
        title: "Info",
        description: "Please complete the current step before adding a new one",
        variant: "default"
      });
      return;
    }
    
    setIsAddingNewStep(true);
    setNewStepData({
      test_step_description: '',
      page: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    });
  };

  const handleSaveNewStep = () => {
    if (!newStepData.test_step_description.trim()) {
      toast({
        title: "Error",
        description: "Test step description is required",
        variant: "destructive"
      });
      return;
    }

    const newStep: TestStep = {
      id: Date.now() + Math.random(),
      tc_id: 'TC001',
      step_no: testSteps.length + 1,
      ...newStepData
    };

    const updatedSteps = [...testSteps, newStep];
    onTestStepsChange(updatedSteps);
    setIsAddingNewStep(false);
    setNewStepData({
      test_step_description: '',
      page: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    });
    
    toast({
      title: "Step Added",
      description: "New test step has been added successfully",
    });
  };

  const handleCancelNewStep = () => {
    setIsAddingNewStep(false);
    setNewStepData({
      test_step_description: '',
      page: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    });
  };

  const updateNewStepData = (field: string, value: string) => {
    console.log('updateNewStepData called:', { field, value });
    setNewStepData(prev => {
      const normalizedValue = field === 'action_type' ? normalizeActionType(value) : value;
      const updated = { ...prev, [field]: normalizedValue };
      
      // If page is changed, clear element_name and xpath to avoid confusion
      if (field === 'page') {
        updated.element_name = '';
        updated.xpath = '';
      }
      
      console.log('updateNewStepData result:', updated);
      return updated;
    });
  };

  // Page dropdown data
  const [pages, setPages] = useState<{ id: number; page_name: string }[]>([]);
  const [loadingPages, setLoadingPages] = useState<boolean>(false);
  
  // Page objects data for dropdowns
  const [pageObjects, setPageObjects] = useState<{
    all_objects: Array<{
      page_name: string;
      object_name: string;
      xpath: string;
      display_name: string;
    }>;
    pages_data: Record<string, Array<{
      object_name: string;
      xpath: string;
    }>>;
  }>({ all_objects: [], pages_data: {} });
  const [loadingPageObjects, setLoadingPageObjects] = useState<boolean>(false);

  useEffect(() => {
    const loadPages = async () => {
      try {
        setLoadingPages(true);
        const res = await fetch(buildApiUrl('/api/page-names'));
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || 'Failed to load pages');
        setPages(data || []);
      } catch (e) {
        console.error('Load pages error:', e);
      } finally {
        setLoadingPages(false);
      }
    };
    
    const loadPageObjects = async () => {
      try {
        setLoadingPageObjects(true);
        const res = await fetch(buildApiUrl('/api/page-objects/dropdown'));
        const data = await res.json();
        if (!res.ok) throw new Error(data?.error || 'Failed to load page objects');
        
        console.log('Loaded page objects data:', data);
        setPageObjects(data || { all_objects: [], pages_data: {} });
      } catch (e) {
        console.error('Load page objects error:', e);
      } finally {
        setLoadingPageObjects(false);
      }
    };
    
    loadPages();
    loadPageObjects();
  }, []);

  const refetchMappedExcelSheet = async () => {
    const caseNameToUse = testCaseName || 'Unknown Test Case';

    try {
      console.log('[FETCH_EXCEL] Fetching mapped Excel for test case:', caseNameToUse);
      const res = await fetch(buildApiUrl(`/api/testcases/${encodeURIComponent(caseNameToUse)}/mapped-excel`));
      if (res.ok) {
        const data = await res.json();
        console.log('[FETCH_EXCEL] Response:', data);
        const mappedSheet = data.excelSheetName || '';
        const sheetsFromApi = Array.isArray(data.availableSheets) ? data.availableSheets : [];
        const mergedSheets = mappedSheet && !sheetsFromApi.includes(mappedSheet)
          ? [mappedSheet, ...sheetsFromApi]
          : sheetsFromApi;

        setMappedExcelSheet(mappedSheet);
        setMappedExcelFileId(
          typeof data.excelFileId === 'number' ? data.excelFileId : Number(data.excelFileId) || null
        );
        setAvailableMappedSheets(mergedSheets);
      } else {
        console.warn('[FETCH_EXCEL] API returned non-ok status:', res.status);
        setMappedExcelSheet('');
        setMappedExcelFileId(null);
        setAvailableMappedSheets([]);
      }
    } catch (error) {
      console.error('[FETCH_EXCEL] Error fetching mapped Excel sheet:', error);
      setMappedExcelSheet('');
      setMappedExcelFileId(null);
      setAvailableMappedSheets([]);
    }
  };

  const handleMappedSheetChange = async (sheetName: string) => {
    if (!sheetName || !mappedExcelFileId) {
      return;
    }

    const caseNameToUse = testCaseName || 'Unknown Test Case';
    const userEmail = localStorage.getItem('userEmail') || 'anonymous';
    setMappedExcelSheet(sheetName);
    setIsUpdatingMappedSheet(true);

    try {
      const parseResponse = await fetch(
        buildApiUrl(`/api/excel-files/${mappedExcelFileId}/parse?sheet_name=${encodeURIComponent(sheetName)}`),
        {
          headers: {
            'X-User-Email': userEmail
          }
        }
      );

      if (!parseResponse.ok) {
        const parseError = await parseResponse.json().catch(() => ({}));
        throw new Error(parseError.error || 'Failed to parse selected sheet');
      }

      const parseData = await parseResponse.json();
      const dataSets = parseData.data_sets ?? 0;

      const updateResponse = await fetch(buildApiUrl(`/api/testcases/${encodeURIComponent(caseNameToUse)}/mapped-excel`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Email': userEmail
        },
        body: JSON.stringify({
          excelFileId: mappedExcelFileId,
          sheetName,
          dataSets
        })
      });

      if (!updateResponse.ok) {
        const errorData = await updateResponse.json().catch(() => ({}));
        throw new Error(errorData.error || 'Failed to update sheet mapping');
      }

      toast({
        title: "Sheet Updated",
        description: `Mapped to "${sheetName}" successfully`,
      });

      await refetchMappedExcelSheet();
    } catch (error) {
      console.error('[UPDATE_SHEET] Failed to update mapped sheet:', error);
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Could not update mapped sheet",
        variant: "destructive"
      });
      await refetchMappedExcelSheet();
    } finally {
      setIsUpdatingMappedSheet(false);
    }
  };

  const handleDeleteMappedExcel = async () => {
    if (!mappedExcelSheet) {
      toast({
        title: "No Mapping",
        description: "No Excel sheet is currently mapped to this test case",
        variant: "destructive"
      });
      return;
    }

    if (!confirm('Are you sure you want to delete this Excel mapping? This action cannot be undone.')) {
      return;
    }

    const caseNameToUse = testCaseName || 'Unknown Test Case';

    try {
      console.log('[DELETE_EXCEL] Deleting mapped Excel for test case:', caseNameToUse);
      const res = await fetch(buildApiUrl(`/api/testcases/${encodeURIComponent(caseNameToUse)}/mapped-excel`), {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Email': localStorage.getItem('userEmail') || 'anonymous'
        }
      });

      if (res.ok) {
        const data = await res.json();
        console.log('[DELETE_EXCEL] Success:', data);
        setMappedExcelSheet('');
        toast({
          title: "Mapping Deleted",
          description: "Excel mapping has been successfully removed from this test case",
        });
      } else {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.error || `Failed to delete mapping (Status: ${res.status})`);
      }
    } catch (error) {
      console.error('[DELETE_EXCEL] Error:', error);
      toast({
        title: "Delete Failed",
        description: error instanceof Error ? error.message : "Failed to delete Excel mapping",
        variant: "destructive"
      });
    }
  };

  useEffect(() => {
    refetchMappedExcelSheet();
  }, [testCaseName]);

  // AUTO-REFRESH XPATH HOOK
  const { triggerRefresh } = useAutoXPathRefresh(
    testSteps,
    pageObjects.all_objects,
    onTestStepsChange,
    (notification) => {
      // Show toast notification to user
      toast({
        title: "✅ XPath Auto-Updated",
        description: `${notification.object_name} on ${notification.page_name} was updated. Step(s) ${notification.affected_steps.join(', ')} refreshed automatically.`,
        duration: 5000,
      });

      console.log('📢 [XPath Refresh Notification]:', notification);
    },
    onAutoXPathRefresh
  );

  // Helper function to get objects for selected page
  const getObjectsForPage = (pageName: string) => {
    return pageObjects.pages_data[pageName] || [];
  };

  // Helper function to check if an element name exists in available options
  const isElementNameValid = (elementName: string, pageName?: string) => {
    if (!elementName) return false;
    
    if (pageName) {
      // Check if element exists in the specific page
      const pageObjectsForPage = getObjectsForPage(pageName);
      return pageObjectsForPage.some(obj => obj.object_name === elementName);
    } else {
      // Check if element exists in all objects
      return pageObjects.all_objects.some(obj => obj.object_name === elementName);
    }
  };

  // Helper function to handle element selection and auto-populate xpath
  const handleElementSelection = (elementName: string, isNewStep: boolean = false, stepId?: number, currentPage?: string) => {
    console.log('handleElementSelection called:', { elementName, isNewStep, stepId, currentPage });
    
    // Find the selected object to get its xpath
    // If we have a current page, prioritize objects from that page
    let selectedObject;
    
    if (currentPage) {
      selectedObject = pageObjects.all_objects.find(obj => 
        obj.object_name === elementName && obj.page_name === currentPage
      );
    } else {
      selectedObject = pageObjects.all_objects.find(obj => obj.object_name === elementName);
    }
    
    console.log('selectedObject found:', selectedObject);
    
    if (selectedObject) {
      if (isNewStep) {
        // Update new step data
        setNewStepData(prev => ({
          ...prev,
          element_name: elementName,
          xpath: selectedObject.xpath,
          page: selectedObject.page_name
        }));
      } else if (stepId) {
        // Update existing step - use single update to avoid race conditions
        const currentStep = testSteps.find(s => s.id === stepId);
        const updates: Partial<TestStep> = {
          element_name: elementName,
          xpath: selectedObject.xpath
        };
        
        // Only update page if it's not already set
        if (!currentStep?.page) {
          updates.page = selectedObject.page_name;
        }
        
        updateStepMultiple(stepId, updates);
      }
    } else {
      // Manual entry - just update element name
      if (isNewStep) {
        setNewStepData(prev => ({
          ...prev,
          element_name: elementName
        }));
      } else if (stepId) {
        updateStep(stepId, 'element_name', elementName);
      }
    }
  };

  return (
    <Card className="bg-white backdrop-blur-sm border-gray-200">
      <CardHeader>
        <CardTitle className="text-lg text-gray-900 flex items-center justify-between">
          <span>Test Steps Grid ({testSteps.length} steps)</span>
          <div className="flex items-center space-x-2">
            {!readOnlyMode && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setIsExcelSidebarOpen(true)}
                  className="border-blue-200 text-blue-600 hover:bg-blue-50"
                >
                  <Database className="w-4 h-4 mr-2" />
                  Select Value
                </Button>
                <select
                  value={mappedExcelSheet || ''}
                  onChange={(e) => handleMappedSheetChange(e.target.value)}
                  disabled={!mappedExcelFileId || isUpdatingMappedSheet || availableMappedSheets.length === 0}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-gray-50 text-gray-700 w-48 disabled:text-gray-400 disabled:bg-gray-100"
                >
                  {!mappedExcelSheet && (
                    <option value="">No Excel sheet mapped</option>
                  )}
                  {availableMappedSheets.map((sheet) => (
                    <option key={sheet} value={sheet}>
                      {sheet}
                    </option>
                  ))}
                </select>
                {mappedExcelSheet && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleDeleteMappedExcel}
                    className="text-red-500 hover:text-red-700 hover:bg-red-50"
                    title="Delete Excel mapping"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                )}
              </>
            )}
            {readOnlyMode && (
              <Badge variant="outline" className="bg-orange-50 border-orange-200 text-orange-700">
                📖 Read-Only Mode
              </Badge>
            )}
          </div>
        </CardTitle>
        {readOnlyMode && (
          <p className="text-sm text-orange-600 mt-1">
            Test steps cannot be modified in read-only mode. Use the main development workflow to create and edit steps.
          </p>
        )}
      </CardHeader>
      <CardContent>
        {testSteps.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <PlusCircle className="w-8 h-8 text-gray-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">No Test Steps</h3>
            <p className="text-gray-500 mb-4">
              {readOnlyMode
                ? "No test steps are available for this test case. Test steps are read-only in this view."
                : "Start by adding your first test step using the Add Step button"
              }
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse border border-gray-200">
              <thead>
                <tr className="bg-gray-50">
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-16">
                    Step #
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 min-w-[200px]">
                    Description
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-40">
                    Page
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-32">
                    Element Name
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-40">
                    Action Type
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 w-32">
                    Values
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-left text-sm font-medium text-gray-700 min-w-[200px]">
                    XPath
                  </th>
                  <th className="border border-gray-200 px-4 py-3 text-center text-sm font-medium text-gray-700 w-40">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {/* New Step Input Row */}
                {isAddingNewStep && !readOnlyMode && (
                  <tr className="bg-blue-50 border-2 border-blue-200">
                    {/* Step Number */}
                    <td className="border border-gray-200 px-4 py-3 text-center">
                      <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center text-white font-bold text-sm mx-auto">
                        {testSteps.length + 1}
                      </div>
                    </td>

                    {/* Description */}
                    <td className="border border-gray-200 px-4 py-3">
                      <Textarea
                        value={newStepData.test_step_description}
                        onChange={(e) => updateNewStepData('test_step_description', e.target.value)}
                        placeholder="Describe what this step does... *"
                        className="w-full min-h-[60px] border-blue-300 focus:border-blue-500"
                        rows={2}
                        autoFocus
                      />
                    </td>

                    {/* Page */}
                    <td className="border border-gray-200 px-4 py-3">
                      <select
                        value={newStepData.page}
                        onChange={(e) => updateNewStepData('page', e.target.value)}
                        className="w-full px-3 py-2 border border-blue-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      >
                        <option value="">Select Page</option>
                        {pages.map(p => (
                          <option key={p.id} value={p.page_name}>{p.page_name}</option>
                        ))}
                      </select>
                    </td>

                    {/* Element Name */}
                    <td className="border border-gray-200 px-4 py-3">
                      <div className="space-y-2">
                        <select
                          value={newStepData.element_name && isElementNameValid(newStepData.element_name, newStepData.page) ? newStepData.element_name : ''}
                          onChange={(e) => {
                            const selectedValue = e.target.value;
                            if (selectedValue === '__manual__') {
                              // Switch to manual entry mode
                              updateNewStepData('element_name', '');
                            } else {
                              handleElementSelection(selectedValue, true);
                            }
                          }}
                          className="w-full px-3 py-2 border border-blue-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                        >
                          <option value="">{loadingPageObjects ? 'Loading elements...' : 'Select Element'}</option>
                          {!loadingPageObjects && newStepData.page && getObjectsForPage(newStepData.page).map((obj, index) => (
                            <option key={`${newStepData.page}-${obj.object_name}-${index}`} value={obj.object_name}>
                              {obj.object_name}
                            </option>
                          ))}
                          {!loadingPageObjects && !newStepData.page && pageObjects.all_objects.map((obj, index) => (
                            <option key={`${obj.page_name}-${obj.object_name}-${index}`} value={obj.object_name}>
                              {obj.display_name}
                            </option>
                          ))}
                          
                        </select>
                        
                        {/* Always show manual input field for full freedom */}
                        <div className="relative">
                          <Input
                            value={newStepData.element_name}
                            onChange={(e) => updateNewStepData('element_name', e.target.value)}
                            placeholder="Type any element name (full freedom to write custom names)"
                            className="w-full text-sm border-blue-300 focus:border-blue-500"
                            autoFocus={!newStepData.element_name}
                          />
                          
                        </div>
                      </div>
                    </td>

                    {/* Action Type */}
                    <td className="border border-gray-200 px-4 py-3">
                      <select
                        value={normalizeActionType(newStepData.action_type)}
                        onChange={(e) => updateNewStepData('action_type', e.target.value)}
                        className="w-full px-3 py-2 border border-blue-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      >
                        {ACTION_TYPES.map(action => (
                          <option key={action} value={action}>{action}</option>
                        ))}
                      </select>
                    </td>

                    {/* Values */}
                    <td className="border border-gray-200 px-4 py-3">
                      <Input
                        value={newStepData.values}
                        onChange={(e) => updateNewStepData('values', e.target.value)}
                        placeholder="Input values"
                        className="w-full border-blue-300 focus:border-blue-500"
                      />
                    </td>

                    {/* XPath */}
                    <td className="border border-gray-200 px-4 py-3">
                      <div className="relative">
                        <Input
                          value={newStepData.xpath}
                          onChange={(e) => updateNewStepData('xpath', e.target.value)}
                          placeholder="Element XPath (auto-populated when element selected)"
                          className="w-full font-mono text-xs border-blue-300 focus:border-blue-500"
                        />
                        {newStepData.xpath && pageObjects.all_objects.find(obj => 
                          obj.object_name === newStepData.element_name && obj.xpath === newStepData.xpath
                        ) && (
                          <div className="absolute right-2 top-2 text-green-500 text-xs">
                            ✓ Auto
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="border border-gray-200 px-4 py-3">
                      <div className="flex items-center justify-center space-x-1">
                        <Button
                          size="sm"
                          onClick={handleSaveNewStep}
                          className="bg-green-500 hover:bg-green-600 h-8 w-8 p-0"
                        >
                          <Save className="w-3 h-3" />
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={handleCancelNewStep}
                          className="h-8 w-8 p-0 border-red-200 text-red-600"
                        >
                          <X className="w-3 h-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                )}

                {testSteps.map((step, index) => (
                  <tr key={step.id} className="hover:bg-gray-50">
                    {/* Step Number */}
                    <td className="border border-gray-200 px-4 py-3 text-center">
                      <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white font-bold text-sm mx-auto">
                        {step.step_no}
                      </div>
                    </td>

                    {/* Description */}
                    <td className="border border-gray-200 px-4 py-3">
                      <Textarea
                        value={step.test_step_description || ''}
                        onChange={(e) => !readOnlyMode && updateStep(step.id, 'test_step_description', e.target.value)}
                        placeholder="Describe what this step does..."
                        className={`w-full min-h-[60px] ${readOnlyMode ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                        rows={2}
                        disabled={readOnlyMode}
                      />
                    </td>

                    {/* Page */}
                    <td className="border border-gray-200 px-4 py-3">
                      <select
                        value={step.page || ''}
                        onChange={(e) => !readOnlyMode && updateStep(step.id, 'page', e.target.value)}
                        className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm ${readOnlyMode ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                        disabled={readOnlyMode}
                      >
                        <option value="">Select Page</option>
                        {pages.map(p => (
                          <option key={p.id} value={p.page_name}>{p.page_name}</option>
                        ))}
                      </select>
                    </td>

                    {/* Element Name */}
                    <td className="border border-gray-200 px-4 py-3">
                      <div className="space-y-2">
                        <select
                          value={step.element_name && isElementNameValid(step.element_name, step.page) ? step.element_name : ''}
                          onChange={(e) => {
                            if (!readOnlyMode) {
                              const selectedValue = e.target.value;
                              if (selectedValue === '__manual__') {
                                // Switch to manual entry mode
                                updateStep(step.id, 'element_name', '');
                              } else {
                                handleElementSelection(selectedValue, false, step.id, step.page);
                              }
                            }
                          }}
                          className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm ${readOnlyMode ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                          disabled={readOnlyMode || loadingPageObjects}
                        >
                          <option value="">{loadingPageObjects ? 'Loading elements...' : 'Select Element'}</option>
                          {!loadingPageObjects && step.page && getObjectsForPage(step.page).map((obj, index) => (
                            <option key={`${step.page}-${obj.object_name}-${index}`} value={obj.object_name}>
                              {obj.object_name}
                            </option>
                          ))}
                          {!loadingPageObjects && !step.page && pageObjects.all_objects.map((obj, index) => (
                            <option key={`${obj.page_name}-${obj.object_name}-${index}`} value={obj.object_name}>
                              {obj.display_name}
                            </option>
                          ))}
                          {!loadingPageObjects && !readOnlyMode && <option value="__manual__">✏️ Type Custom Element Name</option>}
                        </select>
                        
                        {/* Always show manual input field for full freedom */}
                        {!readOnlyMode && (
                          <div className="relative">
                            <Input
                              value={step.element_name || ''}
                              onChange={(e) => updateStep(step.id, 'element_name', e.target.value)}
                              placeholder="Type any element name (full freedom to write custom names)"
                              className="w-full text-sm"
                              autoFocus={!step.element_name}
                            />
                            {!step.element_name && (
                              <div className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 text-xs">
    
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Action Type */}
                    <td className="border border-gray-200 px-4 py-3">
                      <select
                        value={normalizeActionType(step.action_type)}
                        onChange={(e) => !readOnlyMode && updateStep(step.id, 'action_type', e.target.value)}
                        className={`w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm ${readOnlyMode ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                        disabled={readOnlyMode}
                      >
                        {ACTION_TYPES.map(action => (
                          <option key={action} value={action}>{action}</option>
                        ))}
                      </select>
                    </td>

                    {/* Values */}
                    <td className="border border-gray-200 px-4 py-3">
                      <Input
                        value={step.values || ''}
                        onChange={(e) => !readOnlyMode && updateStep(step.id, 'values', e.target.value)}
                        placeholder="Input values"
                        className={`w-full ${readOnlyMode ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                        disabled={readOnlyMode}
                      />
                    </td>

                    {/* XPath */}
                    <td className="border border-gray-200 px-4 py-3">
                      <div className="relative">
                        <Input
                          value={step.xpath || ''}
                          onChange={(e) => !readOnlyMode && updateStep(step.id, 'xpath', e.target.value)}
                          placeholder="Element XPath (auto-populated when element selected)"
                          className={`w-full font-mono text-xs ${readOnlyMode ? 'bg-gray-100 cursor-not-allowed' : ''}`}
                          disabled={readOnlyMode}
                        />
                        {step.xpath && pageObjects.all_objects.find(obj => 
                          obj.object_name === step.element_name && obj.xpath === step.xpath
                        ) && (
                          <div className="absolute right-2 top-2 text-green-500 text-xs">
                            ✓ Auto
                          </div>
                        )}
                      </div>
                    </td>

                    {/* Actions */}
                    <td className="border border-gray-200 px-4 py-3">
                      {readOnlyMode ? (
                        <div className="flex items-center justify-center">
                          <Badge variant="secondary" className="text-xs">Read Only</Badge>
                        </div>
                      ) : (
                        <div className="flex items-center justify-center space-x-1">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => moveStepUp(index)}
                            disabled={index === 0}
                            className="h-8 w-8 p-0"
                          >
                            <ArrowUp className="w-3 h-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => moveStepDown(index)}
                            disabled={index === testSteps.length - 1}
                            className="h-8 w-8 p-0"
                          >
                            <ArrowDown className="w-3 h-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => insertStepAfter(index)}
                            className="border-green-200 text-green-600 h-8 w-8 p-0"
                          >
                            <PlusCircle className="w-3 h-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => deleteStep(step.id)}
                            className="border-red-200 text-red-600 h-8 w-8 p-0"
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      {/* Excel Upload Sidebar */}
      <ExcelUploadSidebar
        isOpen={isExcelSidebarOpen}
        onClose={() => setIsExcelSidebarOpen(false)}
        onMappingSuccess={() => {
          console.log('[MAPPING_SUCCESS] Excel sheet mapped successfully, refetching...');
          refetchMappedExcelSheet();
          setIsExcelSidebarOpen(false);
        }}
        testCaseName={testCaseName || 'Unknown Test Case'}
      />
    </Card>
  );
});

TestStepsGrid.displayName = 'TestStepsGrid';

export default TestStepsGrid;
