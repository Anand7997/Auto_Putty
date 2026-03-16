import React, { useState } from 'react';
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
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
  Minimize2,
  Maximize2,
  Home,
} from 'lucide-react';
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
        icon: isActive ? 'text-white' : 'text-emerald-700',
        bg: isActive 
          ? 'bg-emerald-700 text-white shadow-md border-emerald-700' 
          : isExpanded 
            ? 'bg-emerald-50 border-emerald-200 shadow-sm' 
            : 'hover:bg-emerald-50 border-border hover:border-emerald-200',
        actionBg: 'hover:bg-muted/60',
        actionIcon: 'text-gray-600'
      },
      blue: {
        icon: isActive ? 'text-white' : 'text-blue-700',
        bg: isActive 
          ? 'bg-blue-700 text-white shadow-md border-blue-700' 
          : isExpanded 
            ? 'bg-blue-50 border-blue-200 shadow-sm' 
            : 'hover:bg-blue-50 border-border hover:border-blue-200',
        actionBg: 'hover:bg-muted/60',
        actionIcon: 'text-gray-600'
      },
      purple: {
        icon: isActive ? 'text-white' : 'text-violet-700',
        bg: isActive 
          ? 'bg-violet-700 text-white shadow-md border-violet-700' 
          : isExpanded 
            ? 'bg-violet-50 border-violet-200 shadow-sm' 
            : 'hover:bg-violet-50 border-border hover:border-violet-200',
        actionBg: 'hover:bg-muted/60',
        actionIcon: 'text-gray-600'
      },
      orange: {
        icon: isActive ? 'text-white' : 'text-amber-700',
        bg: isActive 
          ? 'bg-amber-700 text-white shadow-md border-amber-700' 
          : isExpanded 
            ? 'bg-amber-50 border-amber-200 shadow-sm' 
            : 'hover:bg-amber-50 border-border hover:border-amber-200',
        actionBg: 'hover:bg-muted/60',
        actionIcon: 'text-gray-600'
      },
      cyan: {
        icon: isActive ? 'text-white' : 'text-cyan-700',
        bg: isActive 
          ? 'bg-cyan-700 text-white shadow-md border-cyan-700' 
          : isExpanded 
            ? 'bg-cyan-50 border-cyan-200 shadow-sm' 
            : 'hover:bg-cyan-50 border-border hover:border-cyan-200',
        actionBg: 'hover:bg-muted/60',
        actionIcon: 'text-gray-600'
      },
      rose: {
        icon: isActive ? 'text-white' : 'text-rose-700',
        bg: isActive 
          ? 'bg-rose-700 text-white shadow-md border-rose-700' 
          : isExpanded 
            ? 'bg-rose-50 border-rose-200 shadow-sm' 
            : 'hover:bg-rose-50 border-border hover:border-rose-200',
        actionBg: 'hover:bg-muted/60',
        actionIcon: 'text-gray-600'
      }
    };
    return colors[color as keyof typeof colors] || colors.blue;
  };

  return (
    <Sidebar variant="inset" className="border-r border-border">
      <SidebarHeader className="p-4 border-b border-border bg-sidebar">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center shadow-sm">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            {!isCollapsed && (
              <div>
                <h2 className="text-base font-semibold text-foreground">
                  Automation Framework
                </h2>
                <p className="text-xs text-muted-foreground">Professional Testing Suite</p>
              </div>
            )}
          </div>
          <button
            onClick={toggleSidebar}
            className="p-2 hover:bg-accent rounded-md transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? (
              <Maximize2 className="w-4 h-4 text-muted-foreground" />
            ) : (
              <Minimize2 className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        </div>
      </SidebarHeader>

      <SidebarContent className="px-3 py-4 space-y-2">
        {/* Home Button */}
        <div className="mb-4">
          <button
            className={cn(
              "group transition-all duration-200 cursor-pointer border rounded-lg p-4 w-full text-left",
              "hover:bg-accent border-border hover:border-primary/30",
              "flex items-center space-x-3"
            )}
            onClick={() => onHomeClick?.()}
          >
            <div className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center",
              "bg-primary/10 border border-primary/20"
            )}>
              <Home className="w-4 h-4 text-primary" />
            </div>
            
            {!isCollapsed && (
              <div className="flex-1 text-left min-w-0">
                <div className="font-medium text-sm text-foreground">
                  Home Dashboard
                </div>
              </div>
            )}
          </button>
        </div>

        {automationSections.map((section) => {
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
                      isActive ? "bg-white/20" : "bg-card border border-border"
                    )}>
                      <section.icon className={cn("w-4 h-4", colorClasses.icon)} />
                    </div>
                    
                    {!isCollapsed && (
                      <>
                        <div className="flex-1 text-left min-w-0">
                          <div className={cn(
                            "font-medium text-sm",
                            isActive ? "text-white" : "text-foreground"
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
                                  isActive ? "text-white" : "text-muted-foreground"
                                )} />
                              ) : (
                                <ChevronRight className={cn(
                                  "w-4 h-4",
                                  isActive ? "text-white" : "text-muted-foreground"
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
                            "bg-card border border-border hover:bg-muted/60",
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
                            "bg-muted"
                          )}>
                            {isCompleted ? (
                              <CheckCircle className="w-3 h-3 text-green-600" />
                            ) : (
                              <action.icon className={cn(
                                "w-3 h-3", 
                                isCurrentStep ? "text-blue-700" : "text-muted-foreground"
                              )} />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className={cn(
                              "font-medium text-sm",
                              isCurrentStep ? "text-blue-900" : 
                              isCompleted ? "text-green-900" : 
                              "text-foreground"
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
            <div className="bg-emerald-50 p-3 rounded-lg border border-emerald-200 hover:shadow-sm transition-all duration-300">
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
