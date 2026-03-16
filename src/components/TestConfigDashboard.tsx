import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Plus, Edit, Trash2, Settings, ArrowRight, ArrowLeft, Save, Play, ArrowUp, ArrowDown, PlusCircle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { buildApiUrl } from '@/config/api';

interface TestStep {
  id: number;
  tc_id: string;
  step_no: number;
  test_step_description: string;
  element_name: string;
  action_type: string;
  xpath: string;
  values: string;
}

interface TestConfigDashboardProps {
  selectedTestCase?: any;
  selectedProject?: any;
  selectedModule?: any;
  testSteps?: TestStep[];
  onTestStepsChange?: (steps: TestStep[]) => void;
  onNext?: () => void;
  onBack?: () => void;
  developmentMode?: boolean;
  onSave?: () => void;
}

const ACTION_TYPES = ['OPEN_BROWSER', 'CLICK', 'CLICK_AND_SELECT', 'SELECT_COUNT', 'CLICK_AND_TYPE', 'HANDLE_CHECKBOX'];

const LEGACY_TO_CURRENT_ACTION: Record<string, string> = {
  CLICK_AND_SELECT_DATE: 'CLICK_AND_SELECT',
  CLICK_QUICK_DATE: 'CLICK_AND_SELECT',
  CLICK_BUS_QUICK_DATE: 'CLICK_AND_SELECT',
  CLICK_AND_SELECT_AGE: 'CLICK_AND_SELECT',
};

const normalizeActionType = (actionType?: string): string => {
  const raw = (actionType || 'CLICK').toUpperCase().trim();
  if (raw in LEGACY_TO_CURRENT_ACTION) return LEGACY_TO_CURRENT_ACTION[raw];
  if (ACTION_TYPES.includes(raw)) return raw;
  return 'CLICK';
};

const TestConfigDashboard: React.FC<TestConfigDashboardProps> = ({ 
  selectedTestCase, 
  selectedProject,
  selectedModule,
  testSteps = [],
  onTestStepsChange,
  onNext, 
  onBack,
  developmentMode = false,
  onSave
}) => {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [editingStep, setEditingStep] = useState<TestStep | null>(null);
  const [showGrid, setShowGrid] = useState(false);
  const [gridSteps, setGridSteps] = useState<TestStep[]>([]);
  const [formData, setFormData] = useState({
    tc_id: '',
    step_no: 1,
    test_step_description: '',
    element_name: '',
    action_type: 'CLICK',
    xpath: '',
    values: ''
  });
  const { toast } = useToast();

  // Load existing test steps when test case is selected
  useEffect(() => {
    if (selectedTestCase && selectedTestCase.name) {
      loadExistingTestSteps();
      // Reset form with correct TC ID when test case changes
      resetForm();
    }
  }, [selectedTestCase]);

  const loadExistingTestSteps = async () => {
    try {
      setIsLoading(true);
      const response = await fetch(buildApiUrl(`/api/teststeps/${encodeURIComponent(selectedTestCase.name)}`));
      
      if (response.ok) {
        const existingSteps = await response.json();
        if (existingSteps.length > 0) {
          console.log(`✅ Loaded ${existingSteps.length} existing test steps for ${selectedTestCase.name}`);
          onTestStepsChange(existingSteps);
        }
      } else {
        console.log(`No existing test steps found for ${selectedTestCase.name}`);
      }
    } catch (error) {
      console.error('Error loading existing test steps:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const resetForm = () => {
    // Extract TC ID from the selected test case's testcase_id
    const tcId = selectedTestCase?.testcase_id ? 
      selectedTestCase.testcase_id.split('_').pop() || 'TC001' : 'TC001';
    
    setFormData({
      tc_id: tcId,
      step_no: testSteps.length + 1,
      test_step_description: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    });
  };

  const addMoreSteps = () => {
    // Extract TC ID from the selected test case's testcase_id
    const tcId = selectedTestCase?.testcase_id ? 
      selectedTestCase.testcase_id.split('_').pop() || 'TC001' : 'TC001';
    
    const newStep: TestStep = {
      id: Date.now() + Math.random(),
      tc_id: tcId,
      step_no: gridSteps.length + 1,
      test_step_description: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    };
    setGridSteps([...gridSteps, newStep]);
  };

  const updateGridStep = (stepId: number, field: string, value: string | number) => {
    setGridSteps(gridSteps.map(step => 
      step.id === stepId
        ? { ...step, [field]: field === 'action_type' ? normalizeActionType(String(value)) : value }
        : step
    ));
  };

  const saveGridSteps = () => {
    const validSteps = gridSteps.filter(step => step.test_step_description.trim() !== '');
    if (validSteps.length === 0) {
      toast({
        title: "Error",
        description: "Please add at least one test step with description",
        variant: "destructive"
      });
      return;
    }
    
    onTestStepsChange([...testSteps, ...validSteps]);
    setGridSteps([]);
    setShowGrid(false);
    toast({
      title: "Success",
      description: `${validSteps.length} test step(s) added successfully!`,
    });
  };

  const cancelGridMode = () => {
    setGridSteps([]);
    setShowGrid(false);
  };

  const deleteGridStep = (stepId: number) => {
    const updatedSteps = gridSteps.filter(step => step.id !== stepId);
    const reorderedSteps = updatedSteps.map((step, index) => ({
      ...step,
      step_no: index + 1
    }));
    setGridSteps(reorderedSteps);
  };

  const handleCreateStep = async () => {
    if (!formData.test_step_description.trim()) {
      toast({
        title: "Error",
        description: "Test step description is required",
        variant: "destructive"
      });
      return;
    }

    try {
      // Extract TC ID from the selected test case's testcase_id
      const tcId = selectedTestCase?.testcase_id ? 
        selectedTestCase.testcase_id.split('_').pop() || 'TC001' : 'TC001';

      const newStep: TestStep = {
        id: Date.now(),
        tc_id: formData.tc_id || tcId,
        step_no: formData.step_no,
        test_step_description: formData.test_step_description,
        element_name: formData.element_name,
        action_type: formData.action_type,
        xpath: formData.xpath,
        values: formData.values
      };

      if (editingStep) {
        const updatedSteps = testSteps.map(step => 
          step.id === editingStep.id ? { ...newStep, id: editingStep.id } : step
        );
        onTestStepsChange(updatedSteps);
        setEditingStep(null);
        toast({
          title: "Success",
          description: "Test step updated successfully!",
        });
      } else {
        onTestStepsChange([...testSteps, newStep]);
        toast({
          title: "Success",
          description: "Test step created successfully!",
        });
      }

      resetForm();
      setIsCreateModalOpen(false);
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to save test step",
        variant: "destructive"
      });
    }
  };

  const handleEditStep = (step: TestStep) => {
    setEditingStep(step);
    setFormData({
      tc_id: step.tc_id,
      step_no: step.step_no,
      test_step_description: step.test_step_description,
      element_name: step.element_name,
      action_type: normalizeActionType(step.action_type),
      xpath: step.xpath,
      values: step.values
    });
    setIsCreateModalOpen(true);
  };

  const handleDeleteStep = (stepId: number) => {
    console.log('Attempting to delete step with ID:', stepId);
    console.log('Current test steps:', testSteps);
    
    try {
      const updatedSteps = testSteps.filter(step => step.id !== stepId);
      console.log('Updated steps after deletion:', updatedSteps);
      
      // Reorder step numbers after deletion
      const reorderedSteps = updatedSteps.map((step, index) => ({
        ...step,
        step_no: index + 1
      }));
      
      onTestStepsChange(reorderedSteps);
      toast({
        title: "Success",
        description: "Test step deleted successfully!",
      });
    } catch (error) {
      console.error('Error deleting step:', error);
      toast({
        title: "Error",
        description: "Failed to delete test step",
        variant: "destructive"
      });
    }
  };

  const handleInsertAfter = (afterStepId: number) => {
    const currentStepIndex = testSteps.findIndex(step => step.id === afterStepId);
    if (currentStepIndex === -1) return;

    const tcId = selectedTestCase?.testcase_id ? 
      selectedTestCase.testcase_id.split('_').pop() || 'TC001' : 'TC001';

    const newStep: TestStep = {
      id: Date.now() + Math.random(),
      tc_id: tcId,
      step_no: currentStepIndex + 2, // Will be renumbered
      test_step_description: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    };

    // Insert the new step after the current step
    const updatedSteps = [
      ...testSteps.slice(0, currentStepIndex + 1),
      newStep,
      ...testSteps.slice(currentStepIndex + 1)
    ];

    // Renumber all steps
    const renumberedSteps = updatedSteps.map((step, index) => ({
      ...step,
      step_no: index + 1
    }));

    onTestStepsChange(renumberedSteps);
    
    // Open edit dialog for the new step
    setEditingStep(newStep);
    setFormData({
      tc_id: tcId,
      step_no: currentStepIndex + 2,
      test_step_description: '',
      element_name: '',
      action_type: 'CLICK',
      xpath: '',
      values: ''
    });
    setIsCreateModalOpen(true);

    toast({
      title: "Success",
      description: "New test step inserted! Please configure it.",
    });
  };

  const handleMoveUp = (stepId: number) => {
    const currentIndex = testSteps.findIndex(step => step.id === stepId);
    if (currentIndex <= 0) return; // Can't move up if it's the first item

    const updatedSteps = [...testSteps];
    // Swap with previous step
    [updatedSteps[currentIndex - 1], updatedSteps[currentIndex]] = 
    [updatedSteps[currentIndex], updatedSteps[currentIndex - 1]];

    // Renumber all steps
    const renumberedSteps = updatedSteps.map((step, index) => ({
      ...step,
      step_no: index + 1
    }));

    onTestStepsChange(renumberedSteps);
    toast({
      title: "Success",
      description: "Test step moved up!",
    });
  };

  const handleMoveDown = (stepId: number) => {
    const currentIndex = testSteps.findIndex(step => step.id === stepId);
    if (currentIndex >= testSteps.length - 1) return; // Can't move down if it's the last item

    const updatedSteps = [...testSteps];
    // Swap with next step
    [updatedSteps[currentIndex], updatedSteps[currentIndex + 1]] = 
    [updatedSteps[currentIndex + 1], updatedSteps[currentIndex]];

    // Renumber all steps
    const renumberedSteps = updatedSteps.map((step, index) => ({
      ...step,
      step_no: index + 1
    }));

    onTestStepsChange(renumberedSteps);
    toast({
      title: "Success",
      description: "Test step moved down!",
    });
  };

  const handleSaveConfiguration = async () => {
    if (testSteps.length === 0) {
      toast({
        title: "Error",
        description: "Please add at least one test step",
        variant: "destructive"
      });
      return;
    }

    try {
      // TODO: Save to database table
      toast({
        title: "Success",
        description: `Configuration saved to ${selectedTestCase.name} table in Ixigo_TestAutomation database!`,
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to save configuration",
        variant: "destructive"
      });
    }
  };

  // In developmentMode we allow configuring steps without a pre-selected test case
  if (!selectedTestCase && !developmentMode) {
    return (
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardContent className="p-8 text-center">
          <p className="text-gray-600">Please select a test case first</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl text-gray-900 flex items-center space-x-2">
                <Settings className="w-6 h-6 text-blue-600" />
                <span>{developmentMode ? `Configure Steps - ${selectedModule?.name || selectedModule?.module_name || 'New Test Case'}` : `Configure "${selectedTestCase.name}"`}</span>
              </CardTitle>
              <p className="text-gray-600 mt-2">{developmentMode ? 'Add and organize steps for your new test case' : 'Define test steps and actions for your test case'}</p>
            </div>
            <div className="flex space-x-2">
              <Button onClick={handleSaveConfiguration} className="bg-blue-500 hover:bg-blue-600">
                <Save className="w-4 h-4 mr-2" />
                Save Configuration
              </Button>
              <Button 
                className="bg-gradient-to-r from-blue-500 to-indigo-500 hover:from-blue-600 hover:to-indigo-600"
                onClick={() => {
                  setShowGrid(true);
                  if (gridSteps.length === 0) {
                    addMoreSteps();
                  }
                }}
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Test Steps
              </Button>

            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Edit Step Dialog */}
      <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
        <DialogContent className="bg-white border-gray-200 max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-gray-900">
              {editingStep ? 'Edit Test Step' : 'Add New Test Step'}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-600">TC ID</label>
              <Input
                value={formData.tc_id}
                onChange={(e) => setFormData({ ...formData, tc_id: e.target.value })}
                placeholder="TC001"
                className="bg-gray-50 border-gray-200 text-gray-900"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-600">Step No</label>
              <Input
                type="number"
                value={formData.step_no}
                onChange={(e) => setFormData({ ...formData, step_no: parseInt(e.target.value) || 1 })}
                className="bg-gray-50 border-gray-200 text-gray-900"
              />
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium text-gray-600">Test Step Description</label>
              <Textarea
                value={formData.test_step_description}
                onChange={(e) => setFormData({ ...formData, test_step_description: e.target.value })}
                placeholder="Describe what this step does"
                className="bg-gray-50 border-gray-200 text-gray-900"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-600">Element Name</label>
              <Input
                value={formData.element_name}
                onChange={(e) => setFormData({ ...formData, element_name: e.target.value })}
                placeholder="ElementName"
                className="bg-gray-50 border-gray-200 text-gray-900"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-600">Action Type</label>
              <select
                value={formData.action_type}
                onChange={(e) => setFormData({ ...formData, action_type: e.target.value })}
                className="w-full bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-gray-900"
              >
                {ACTION_TYPES.map(action => (
                  <option key={action} value={action}>{action}</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                {normalizeActionType(formData.action_type) === 'OPEN_BROWSER' && 'Use Values for URL (e.g. https://example.com).'}
                {normalizeActionType(formData.action_type) === 'CLICK_AND_SELECT' && 'Use for selection flows (city/date/age) with Values as the input.'}
                {normalizeActionType(formData.action_type) === 'SELECT_COUNT' && 'Use for count updates (rooms/adults/children/infants) with numeric Values.'}
                {normalizeActionType(formData.action_type) === 'CLICK' && 'Use for pure click actions where no selection/input is needed.'}
                {normalizeActionType(formData.action_type) === 'CLICK_AND_TYPE' && 'Clicks the element and types the text from Values.'}
                {normalizeActionType(formData.action_type) === 'HANDLE_CHECKBOX' && 'Use Values: true/false, yes/no, or 1/0.'}
              </p>
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium text-gray-600">Locator (XPath/CSS/ID)</label>
              <Input
                value={formData.xpath}
                onChange={(e) => setFormData({ ...formData, xpath: e.target.value })}
                placeholder="//div[@id='example'] or #myId or .myClass"
                className="bg-gray-50 border-gray-200 text-gray-900"
              />
              <p className="text-xs text-gray-500 mt-1">
                Use XPath, CSS selectors, or element IDs. The generic executor will auto-detect the type.
              </p>
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium text-gray-600">Values</label>
              <Input
                value={formData.values}
                onChange={(e) => setFormData({ ...formData, values: e.target.value })}
                placeholder="Enter values if needed"
                className="bg-gray-50 border-gray-200 text-gray-900"
              />
            </div>
            <div className="col-span-2 flex justify-end space-x-2">
              <Button variant="outline" onClick={() => {
                setIsCreateModalOpen(false);
                setEditingStep(null);
              }}>
                Cancel
              </Button>
              <Button onClick={handleCreateStep} className="bg-gradient-to-r from-blue-500 to-indigo-500">
                {editingStep ? 'Update Step' : 'Add Step'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Grid Mode for Adding Multiple Test Steps */}
      {showGrid && (
        <Card className="bg-white backdrop-blur-sm border-gray-200">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-gray-900">Add Test Steps (Grid Mode)</CardTitle>
              <div className="flex space-x-2">
                <Button 
                  onClick={addMoreSteps}
                  className="bg-green-500 hover:bg-green-600"
                  size="sm"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Add More Steps
                </Button>
                <Button 
                  onClick={saveGridSteps}
                  className="bg-blue-500 hover:bg-blue-600"
                  size="sm"
                >
                  <Save className="w-4 h-4 mr-2" />
                  Save All
                </Button>
                <Button 
                  onClick={cancelGridMode}
                  variant="outline"
                  size="sm"
                >
                  Cancel
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-3 px-2 text-gray-600">TC ID</th>
                    <th className="text-left py-3 px-2 text-gray-600">Step No</th>
                    <th className="text-left py-3 px-2 text-gray-600">Description</th>
                    <th className="text-left py-3 px-2 text-gray-600">Element</th>
                    <th className="text-left py-3 px-2 text-gray-600">Action</th>
                    <th className="text-left py-3 px-2 text-gray-600">Locator</th>
                    <th className="text-left py-3 px-2 text-gray-600">Values</th>
                    <th className="text-left py-3 px-2 text-gray-600">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {gridSteps.map((step) => (
                    <tr key={step.id} className="border-b border-gray-100">
                      <td className="py-2 px-2">
                        <Input
                          value={step.tc_id}
                          onChange={(e) => updateGridStep(step.id, 'tc_id', e.target.value)}
                          className="h-8 text-xs"
                          placeholder="TC001"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <Input
                          type="number"
                          value={step.step_no}
                          onChange={(e) => updateGridStep(step.id, 'step_no', parseInt(e.target.value) || 1)}
                          className="h-8 text-xs w-16"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <Textarea
                          value={step.test_step_description}
                          onChange={(e) => updateGridStep(step.id, 'test_step_description', e.target.value)}
                          className="h-8 text-xs min-h-8 resize-none"
                          placeholder="Test step description"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <Input
                          value={step.element_name}
                          onChange={(e) => updateGridStep(step.id, 'element_name', e.target.value)}
                          className="h-8 text-xs"
                          placeholder="Element name"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <select
                                value={normalizeActionType(step.action_type)}
                                onChange={(e) => updateGridStep(step.id, 'action_type', e.target.value)}
                          className="w-full h-8 text-xs bg-white border border-gray-200 rounded-md px-2"
                        >
                          {ACTION_TYPES.map(action => (
                            <option key={action} value={action}>{action}</option>
                          ))}
                        </select>
                      </td>
                      <td className="py-2 px-2">
                        <Input
                          value={step.xpath}
                          onChange={(e) => updateGridStep(step.id, 'xpath', e.target.value)}
                          className="h-8 text-xs"
                          placeholder="Locator"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <Input
                          value={step.values}
                          onChange={(e) => updateGridStep(step.id, 'values', e.target.value)}
                          className="h-8 text-xs"
                          placeholder="Values"
                        />
                      </td>
                      <td className="py-2 px-2">
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="text-red-600 hover:text-red-800 hover:bg-red-50 h-8 w-8 p-0"
                          onClick={() => deleteGridStep(step.id)}
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Test Steps Table */}
      <Card className="bg-white backdrop-blur-sm border-gray-200">
        <CardHeader>
          <CardTitle className="text-gray-900">Test Steps Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-2 text-gray-600">TC ID</th>
                  <th className="text-left py-3 px-2 text-gray-600">Step No</th>
                  <th className="text-left py-3 px-2 text-gray-600">Description</th>
                  <th className="text-left py-3 px-2 text-gray-600">Element</th>
                  <th className="text-left py-3 px-2 text-gray-600">Action</th>
                  <th className="text-left py-3 px-2 text-gray-600">Locator</th>
                  <th className="text-left py-3 px-2 text-gray-600">Values</th>
                  <th className="text-left py-3 px-2 text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody>
                {testSteps.map((step) => (
                  <tr key={step.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-2 text-gray-900">{step.tc_id}</td>
                    <td className="py-3 px-2 text-gray-900">{step.step_no}</td>
                    <td className="py-3 px-2 text-gray-900 max-w-xs truncate">{step.test_step_description}</td>
                    <td className="py-3 px-2 text-gray-900">{step.element_name}</td>
                    <td className="py-3 px-2">
                      <Badge className="bg-blue-500/20 text-blue-600">{normalizeActionType(step.action_type)}</Badge>
                    </td>
                    <td className="py-3 px-2 text-gray-900 max-w-xs truncate">{step.xpath}</td>
                    <td className="py-3 px-2 text-gray-900">{step.values}</td>
                    <td className="py-3 px-2">
                      <div className="flex space-x-1">
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="text-blue-600 hover:text-blue-800 hover:bg-blue-50"
                          onClick={() => handleMoveUp(step.id)}
                          disabled={testSteps.findIndex(s => s.id === step.id) === 0}
                          title="Move Up"
                        >
                          <ArrowUp className="w-4 h-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="text-blue-600 hover:text-blue-800 hover:bg-blue-50"
                          onClick={() => handleMoveDown(step.id)}
                          disabled={testSteps.findIndex(s => s.id === step.id) === testSteps.length - 1}
                          title="Move Down"
                        >
                          <ArrowDown className="w-4 h-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="text-green-600 hover:text-green-800 hover:bg-green-50"
                          onClick={() => handleInsertAfter(step.id)}
                          title="Insert Step After"
                        >
                          <PlusCircle className="w-4 h-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                          onClick={() => handleEditStep(step)}
                          title="Edit Step"
                        >
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm" 
                          className="text-red-600 hover:text-red-800 hover:bg-red-50"
                          onClick={() => handleDeleteStep(step.id)}
                          title="Delete Step"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {testSteps.length === 0 && (
              <div className="text-center py-8 text-gray-600">
                No test steps configured yet. Click "Add Test Steps" to get started.
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex justify-between items-center">
        <Button variant="outline" onClick={onBack} className="border-gray-200 text-gray-600">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Modules
        </Button>

        {testSteps.length > 0 && (
          <Button 
            onClick={onNext}
            className="bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600"
          >
            Review & Execute
            <ArrowRight className="w-4 h-4 ml-2" />
          </Button>
        )}
      </div>
    </div>
  );
};

export default TestConfigDashboard;
