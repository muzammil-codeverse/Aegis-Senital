/**
 * Lazy-loaded route components for heavy pages.
 * These are code-split via React.lazy so the initial bundle stays small.
 * Each import resolves its own JS chunk when the user first navigates to that page.
 */
import { lazy } from 'react'

export const LazyMapOperationsPage = lazy(() => import('../pages/MapOperationsPage'))
export const LazyAnalyticsPage = lazy(() => import('../pages/AnalyticsPage'))
export const LazyDroneSimulationPage = lazy(() => import('../pages/DroneSimulationPage'))
export const LazyDroneMissionPlannerPage = lazy(() => import('../pages/DroneMissionPlannerPage'))
export const LazyDroneFusionPage = lazy(() => import('../pages/DroneFusionPage'))
export const LazyDroneOperationsHub = lazy(() => import('../pages/DroneOperationsHub'))
export const LazyInvestigationWorkspacePage = lazy(() => import('../pages/InvestigationWorkspacePage'))
export const LazyModelGovernancePage = lazy(() => import('../pages/ModelGovernancePage'))
export const LazyUploadedVideoAnalysisPage = lazy(() => import('../pages/UploadedVideoAnalysisPage'))
