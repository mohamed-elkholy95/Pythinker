/**
 * Canvas API client.
 * Provides typed functions for all canvas API endpoints.
 */
import { apiClient, type ApiResponse } from './client'
import type { CanvasProject, CanvasVersion } from '@/types/canvas'

// --- Request types ---

export interface CreateProjectRequest {
  name?: string
  width?: number
  height?: number
  background?: string
  session_id?: string
}

export interface UpdateProjectRequest {
  name?: string
  pages?: unknown[]
  width?: number
  height?: number
  background?: string
  thumbnail?: string
}

export interface GenerateImageRequest {
  prompt: string
  width?: number
  height?: number
}

export interface EditImageRequest {
  image_url: string
  instruction: string
}

export interface RemoveBackgroundRequest {
  image_url: string
}

export interface AIEditRequest {
  instruction: string
}

// --- Response types ---

export interface ImageResponse {
  urls: string[]
}

interface ProjectListResponse {
  projects: CanvasProject[]
  total: number
}

interface VersionListResponse {
  versions: CanvasVersion[]
  total: number
}

// --- API functions ---

export async function createProject(data: CreateProjectRequest): Promise<CanvasProject> {
  const response = await apiClient.post<ApiResponse<CanvasProject>>('/canvas/projects', data)
  return response.data.data
}

export async function listProjects(skip = 0, limit = 50): Promise<ProjectListResponse> {
  const response = await apiClient.get<ApiResponse<ProjectListResponse>>('/canvas/projects', {
    params: { skip, limit },
  })
  return response.data.data
}

export async function getProject(projectId: string): Promise<CanvasProject> {
  const response = await apiClient.get<ApiResponse<CanvasProject>>(`/canvas/projects/${projectId}`)
  return response.data.data
}

export async function getSessionProject(sessionId: string): Promise<CanvasProject> {
  const response = await apiClient.get<ApiResponse<CanvasProject>>(
    `/canvas/sessions/${sessionId}/project`,
  )
  return response.data.data
}

export async function updateProject(
  projectId: string,
  data: UpdateProjectRequest,
): Promise<CanvasProject> {
  const response = await apiClient.put<ApiResponse<CanvasProject>>(
    `/canvas/projects/${projectId}`,
    data,
  )
  return response.data.data
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiClient.delete(`/canvas/projects/${projectId}`)
}

export async function getVersions(projectId: string): Promise<VersionListResponse> {
  const response = await apiClient.get<ApiResponse<VersionListResponse>>(
    `/canvas/projects/${projectId}/versions`,
  )
  return response.data.data
}

export async function restoreVersion(
  projectId: string,
  version: number,
): Promise<CanvasProject> {
  const response = await apiClient.post<ApiResponse<CanvasProject>>(
    `/canvas/projects/${projectId}/versions/${version}/restore`,
  )
  return response.data.data
}

export async function generateImage(data: GenerateImageRequest): Promise<ImageResponse> {
  const response = await apiClient.post<ApiResponse<ImageResponse>>(
    '/canvas/generate-image',
    data,
  )
  return response.data.data
}

export async function editImage(data: EditImageRequest): Promise<ImageResponse> {
  const response = await apiClient.post<ApiResponse<ImageResponse>>('/canvas/edit-image', data)
  return response.data.data
}

export async function removeBackground(data: RemoveBackgroundRequest): Promise<ImageResponse> {
  const response = await apiClient.post<ApiResponse<ImageResponse>>(
    '/canvas/remove-background',
    data,
  )
  return response.data.data
}

export async function aiEdit(
  projectId: string,
  data: AIEditRequest,
): Promise<CanvasProject> {
  const response = await apiClient.post<ApiResponse<CanvasProject>>(
    `/canvas/projects/${projectId}/ai-edit`,
    data,
  )
  return response.data.data
}
