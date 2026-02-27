import React, { useState } from 'react';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from '@/components/ui/sidebar';
import {
  ChevronDown,
  ChevronRight,
  FileSearch,
  Target,
  Code,
  Play,
  BarChart3,
  Settings,
  Database,
  TestTube,
  FolderOpen,
  GitBranch,
  Layers,
  CheckCircle,
  PlayCircle,
  Activity,
  TrendingUp,
  FileText,
  Wrench,
  AlertTriangle,
  Clock,
  Users,
  Shield,
  Zap,
  Monitor,
  Bug,
  RefreshCw,
  Sparkles,
  List,
  History,
  BarChart,
  ExternalLink,
  Minimize2,
  Maximize2,
  Home,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// Define the main automation workflow sections with professional structure
const automationSections = [
  {
    id: 'requirements',
    title: 'Requirement and Feasibility Analysis',
    shortTitle: 'Requirements & Feasibility',
    icon: FileSearch,
    color: 'emerald',
    gradient: 'from-emerald-500 to-teal-600',
    description: 'Analyze requirements and assess automation feasibility',
    isPlaceholder: false,
    quickActions: [
      { id: 'authorize-users', title: 'Authorize Users', icon: Users, description: 'Manage user authorizations' },
      { id: 'authorize-functions', title: 'Authorize Functions', icon: Settings, description: 'Configure function permissions' },
    ]
 
  },
  {
    id: 'planning',
    title: 'Automation Planning',
    shortTitle: 'Automation Planning',
    icon: Target,
    color: 'blue',
    gradient: 'from-blue-500 to-indigo-600',
    description: 'Plan and structure automation projects',
    isPlaceholder: false,
    quickActions: [
      { id: 'projects', title: 'Projects', icon: Database, description: 'Manage test projects' },
      { id: 'modules', title: 'Modules', icon: TestTube, description: 'Configure project modules' },
      { id: 'test-cases', title: 'Test Cases', icon: FileText, description: 'Manage test cases' },
      { id: 'test-steps', title: 'Test Steps', icon: List, description: 'Configure test steps' },
    ]
  },
  {
    id: 'development',
    title: 'Automation Development',
    shortTitle: 'Automation Development',
    icon: Code,
    color: 'purple',
    gradient: 'from-purple-500 to-violet-600',
    description: 'Develop and maintain automation scripts',
    isPlaceholder: false,
    quickActions: [
      { id: 'dev-projects', title: 'Projects', icon: Database, description: 'Development projects' },
      { id: 'dev-modules', title: 'Modules', icon: TestTube, description: 'Development modules' },
      { id: 'dev-test-cases', title: 'Test Cases', icon: FileText, description: 'Development test cases' },
      { id: 'dev-test-steps', title: 'Test Steps', icon: List, description: 'Development test steps' },
    ]
  },
  {
    id: 'execution',
    title: 'Test Lab',
    shortTitle: 'Test Lab',
    icon: Play,
    color: 'orange',
    gradient: 'from-orange-500 to-red-500',
    description: 'Execute tests and monitor results',
    isPlaceholder: false,
    quickActions: [
      { id: 'test-suite', title: 'Test Suite', icon: TestTube, description: 'Manage test suites' },
      { id: 'run-execution', title: 'Execute Tests', icon: PlayCircle, description: 'Run selected tests' },
      { id: 'live-monitor', title: 'Live Monitor', icon: Monitor, description: 'Monitor execution' },
    ]
  },
  {
    id: 'reporting',
    title: 'Reporting',
    shortTitle: 'Reporting',
    icon: BarChart3,
    color: 'cyan',
    gradient: 'from-cyan-500 to-blue-600',
    description: 'View reports and execution history',
    isPlaceholder: false,
    quickActions: [
      { id: 'execution-history', title: 'Execution History', icon: History, description: 'View test execution history' },
      { id: 'allure-reports', title: 'Allure Reports', icon: BarChart, description: 'Interactive test reports' },
      { id: 'analytics', title: 'Analytics', icon: TrendingUp, description: 'Test analytics and trends' },
    ]
  },
  {
    id: 'maintenance',
    title: 'Maintenance',
    shortTitle: 'Maintenance',
    icon: Settings,
    color: 'rose',
    gradient: 'from-rose-500 to-pink-600',
    description: 'Maintain and optimize automation assets',
    isPlaceholder: false,
    quickActions: [
      { id: 'system-health', title: 'System Health', icon: Activity, description: 'Monitor system status' },
      { id: 'asset-management', title: 'Asset Management', icon: FolderOpen, description: 'Manage test assets' },
      { id: 'optimization', title: 'Optimization', icon: Zap, description: 'Optimize test performance' },
      { id: 'scheduling', title: 'Maintenance Scheduling', icon: Clock, description: 'Schedule maintenance tasks' },
      { id: 'security', title: 'Security & Compliance', icon: Shield, description: 'Security monitoring' },
      { id: 'troubleshooting', title: 'Diagnostics', icon: Bug, description: 'Troubleshooting tools' },
      { id: 'cleanup', title: 'Cleanup Tools', icon: RefreshCw, description: 'Clean up old data' },
      { id: 'backup', title: 'Backup & Recovery', icon: Shield, description: 'Backup and restore data' }
    ]
  }
];

interface NavigationFlow {
  currentStep: number;
  sectionId: string;
  steps: string[];
}

interface ProfessionalSidebarProps {
  onSectionAction?: (sectionId: string, actionId: string) => void;
  onQuickAction?: (actionId: string) => void;
  navigationFlow?: NavigationFlow;
  onSectionSelect?: (sectionId: string) => void;
  onHomeClick?: () => void;
}

export function ProfessionalSidebar({ onSectionAction, onQuickAction, navigationFlow, onSectionSelect, onHomeClick }: ProfessionalSidebarProps) {
  const { state, toggleSidebar } = useSidebar();
  const isCollapsed = state === 'collapsed';
  const [expandedSections, setExpandedSections] = useState<string[]>([]);
  const [activeSections, setActiveSections] = useState<string[]>([]);

  const toggleSection = (sectionId: string) => {
    setExpandedSections(prev => 
      prev.includes(sectionId) 
        ? prev.filter(id => id !== sectionId)
        : [...prev, sectionId]
    );
  };

  const handleSectionClick = (sectionId: string) => {
    if (isCollapsed) {
      // If collapsed, expand the section and show it
      setExpandedSections(prev => 
        prev.includes(sectionId) ? prev : [...prev, sectionId]
      );
    }
    setActiveSections(prev => 
      prev.includes(sectionId) 
        ? prev.filter(id => id !== sectionId)
        : [...prev, sectionId]
    );

    // Notify parent that a section header was selected
    onSectionSelect?.(sectionId);
  };

  const handleQuickActionClick = (sectionId: string, actionId: string) => {
    onSectionAction?.(sectionId, actionId);
    onQuickAction?.(actionId);
  };

  const getColorClasses = (color: string, isActive: boolean = false, isExpanded: boolean = false) => {
    const colors = {
      emerald: {
        icon: isActive ? 'text-white' : 'text-emerald-600',
        bg: isActive 
          ? 'bg-emerald-600 text-white shadow-md border-emerald-600' 
          : isExpanded 
            ? 'bg-emerald-50 border-emerald-200' 
            : 'hover:bg-emerald-50 border-gray-200 hover:border-emerald-200',
        badge: 'bg-emerald-100 text-emerald-700 border-emerald-200',
        actionBg: 'hover:bg-gray-50',
        actionIcon: 'text-gray-600'
      },
      blue: {
        icon: isActive ? 'text-white' : 'text-blue-600',
        bg: isActive 
          ? 'bg-blue-600 text-white shadow-md border-blue-600' 
          : isExpanded 
            ? 'bg-blue-50 border-blue-200' 
            : 'hover:bg-blue-50 border-gray-200 hover:border-blue-200',
        badge: 'bg-blue-100 text-blue-700 border-blue-200',
        actionBg: 'hover:bg-gray-50',
        actionIcon: 'text-gray-600'
      },
      purple: {
        icon: isActive ? 'text-white' : 'text-purple-600',
        bg: isActive 
          ? 'bg-purple-600 text-white shadow-md border-purple-600' 
          : isExpanded 
            ? 'bg-purple-50 border-purple-200' 
            : 'hover:bg-purple-50 border-gray-200 hover:border-purple-200',
        badge: 'bg-purple-100 text-purple-700 border-purple-200',
        actionBg: 'hover:bg-gray-50',
        actionIcon: 'text-gray-600'
      },
      orange: {
        icon: isActive ? 'text-white' : 'text-orange-600',
        bg: isActive 
          ? 'bg-orange-600 text-white shadow-md border-orange-600' 
          : isExpanded 
            ? 'bg-orange-50 border-orange-200' 
            : 'hover:bg-orange-50 border-gray-200 hover:border-orange-200',
        badge: 'bg-orange-100 text-orange-700 border-orange-200',
        actionBg: 'hover:bg-gray-50',
        actionIcon: 'text-gray-600'
      },
      cyan: {
        icon: isActive ? 'text-white' : 'text-cyan-600',
        bg: isActive 
          ? 'bg-cyan-600 text-white shadow-md border-cyan-600' 
          : isExpanded 
            ? 'bg-cyan-50 border-cyan-200' 
            : 'hover:bg-cyan-50 border-gray-200 hover:border-cyan-200',
        badge: 'bg-cyan-100 text-cyan-700 border-cyan-200',
        actionBg: 'hover:bg-gray-50',
        actionIcon: 'text-gray-600'
      },
      rose: {
        icon: isActive ? 'text-white' : 'text-rose-600',
        bg: isActive 
          ? 'bg-rose-600 text-white shadow-md border-rose-600' 
          : isExpanded 
            ? 'bg-rose-50 border-rose-200' 
            : 'hover:bg-rose-50 border-gray-200 hover:border-rose-200',
        badge: 'bg-rose-100 text-rose-700 border-rose-200',
        actionBg: 'hover:bg-gray-50',
        actionIcon: 'text-gray-600'
      }
    };
    return colors[color as keyof typeof colors] || colors.blue;
  };

  return (
    <Sidebar variant="inset" className="cursor-glow border-r border-gray-200">
      <SidebarHeader className="p-4 border-b bg-gradient-to-r from-slate-50 to-gray-50">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 via-purple-500 to-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            {!isCollapsed && (
              <div>
                <h2 className="text-lg font-bold bg-gradient-to-r from-gray-800 to-gray-600 bg-clip-text text-transparent">
                  Automation Framework
                </h2>
                <p className="text-xs text-gray-500 font-medium">Professional Testing Suite</p>
              </div>
            )}
          </div>
          <button
            onClick={toggleSidebar}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? (
              <Maximize2 className="w-4 h-4 text-gray-600" />
            ) : (
              <Minimize2 className="w-4 h-4 text-gray-600" />
            )}
          </button>
        </div>
      </SidebarHeader>

      <SidebarContent className="px-3 py-4 space-y-2 sidebar-scroll">
        {/* Home Button */}
        <div className="mb-4">
          <button
            className={cn(
              "group transition-all duration-200 cursor-pointer border rounded-lg p-4 w-full text-left",
              "hover:bg-blue-50 border-gray-200 hover:border-blue-200",
              "flex items-center space-x-3"
            )}
            onClick={() => onHomeClick?.()}
          >
            <div className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center",
              "bg-blue-100 border border-blue-200"
            )}>
              <Home className="w-4 h-4 text-blue-600" />
            </div>
            
            {!isCollapsed && (
              <div className="flex-1 text-left min-w-0">
                <div className="font-medium text-sm text-gray-900">
                  Home Dashboard
                </div>
              </div>
            )}
          </button>
        </div>

        {automationSections.map((section, sectionIndex) => {
          const isExpanded = expandedSections.includes(section.id);
          const isActive = activeSections.includes(section.id);
          const colorClasses = getColorClasses(section.color, isActive, isExpanded);

          return (
            <div key={section.id} className="space-y-1">
              {/* Main Section Button */}
              <div>
                <button
                  className={cn(
                    "group transition-all duration-200 cursor-pointer border rounded-lg p-4 w-full text-left",
                    colorClasses.bg,
                    section.isPlaceholder && "opacity-75 cursor-not-allowed"
                  )}
                  onClick={() => {
                    if (!section.isPlaceholder) {
                      handleSectionClick(section.id);
                      if (!isCollapsed) {
                        toggleSection(section.id);
                      }
                    }
                  }}
                  disabled={section.isPlaceholder}
                >
                  <div className="flex items-center space-x-3 w-full">
                    <div className={cn(
                      "w-8 h-8 rounded-lg flex items-center justify-center",
                      isActive ? "bg-white/20" : "bg-white border border-gray-200"
                    )}>
                      <section.icon className={cn("w-4 h-4", colorClasses.icon)} />
                    </div>
                    
                    {!isCollapsed && (
                      <>
                        <div className="flex-1 text-left min-w-0">
                          <div className={cn(
                            "font-medium text-sm",
                            isActive ? "text-white" : "text-gray-900"
                          )}>
                            {section.shortTitle}
                          </div>
                        </div>
                        
                        <div className="flex items-center space-x-2 flex-shrink-0">
                          {!section.isPlaceholder && (
                            <>
                              {isExpanded ? (
                                <ChevronDown className={cn(
                                  "w-4 h-4",
                                  isActive ? "text-white" : "text-gray-400"
                                )} />
                              ) : (
                                <ChevronRight className={cn(
                                  "w-4 h-4",
                                  isActive ? "text-white" : "text-gray-400"
                                )} />
                              )}
                            </>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                </button>
              </div>

              {/* Sub-buttons */}
              {isExpanded && !isCollapsed && !section.isPlaceholder && (
                <div className="ml-6 mt-1 space-y-1">
                  {section.quickActions.map((action, index) => {
                    // Check if this action is currently active in the navigation flow
                    const isCurrentStep = navigationFlow && 
                      navigationFlow.sectionId === section.id && 
                      navigationFlow.currentStep === index;
                    
                    // Check if this step is completed
                    const isCompleted = navigationFlow && 
                      navigationFlow.sectionId === section.id && 
                      navigationFlow.currentStep > index;
                    
                    return (
                      <div key={action.id}>
                        <button
                          className={cn(
                            "group transition-all duration-200 cursor-pointer rounded-lg p-3 text-sm w-full text-left",
                            "bg-white border border-gray-200 hover:bg-gray-50",
                            "flex items-center space-x-3",
                            isCurrentStep && "bg-blue-50 border-blue-200",
                            isCompleted && "bg-green-50 border-green-200"
                          )}
                          onClick={() => handleQuickActionClick(section.id, action.id)}
                        >
                          <div className={cn(
                            "w-6 h-6 rounded flex items-center justify-center",
                            isCurrentStep ? "bg-blue-100" : 
                            isCompleted ? "bg-green-100" : 
                            "bg-gray-100"
                          )}>
                            {isCompleted ? (
                              <CheckCircle className="w-3 h-3 text-green-600" />
                            ) : (
                              <action.icon className={cn(
                                "w-3 h-3", 
                                isCurrentStep ? "text-blue-600" : "text-gray-600"
                              )} />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className={cn(
                              "font-medium text-sm",
                              isCurrentStep ? "text-blue-900" : 
                              isCompleted ? "text-green-900" : 
                              "text-gray-700"
                            )}>
                              {action.title}
                            </div>
                          </div>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}



        {/* System Status */}
        {!isCollapsed && (
          <div className="mt-4">
            <div className="bg-gradient-to-r from-green-50 to-emerald-50 p-3 rounded-lg border border-green-200 hover:shadow-md transition-all duration-300">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="w-2.5 h-2.5 bg-green-400 rounded-full animate-pulse shadow-lg shadow-green-400/50" />
                  <span className="text-sm font-semibold text-green-800">System Online</span>
                </div>
                <Activity className="w-4 h-4 text-green-600" />
              </div>
              <div className="text-xs text-green-600 mt-1 font-medium">All services operational</div>
            </div>
          </div>
        )}
      </SidebarContent>

      <SidebarRail />
    </Sidebar>
  );
}