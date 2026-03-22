/**
 * Projects API client.
 * Provides typed functions for project CRUD endpoints.
 */
import { apiClient, type ApiResponse } from './client'
import type { Project, ProjectListItem, CreateProjectRequest, UpdateProjectRequest } from '@/types/project'

export async function createProject(data: CreateProjectRequest): Promise<Project> {
  const response = await apiClient.post<ApiResponse<Project>>('/projects', data)
  return response.data.data
}

export async function listProjects(
  params?: { status?: string; limit?: number; offset?: number },
): Promise<ProjectListItem[]> {
  const response = await apiClient.get<ApiResponse<ProjectListItem[]>>('/projects', { params })
  return response.data.data
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await apiClient.get<ApiResponse<Project>>(`/projects/${projectId}`)
  return response.data.data
}

export async function updateProject(
  projectId: string,
  data: UpdateProjectRequest,
): Promise<Project> {
  const response = await apiClient.patch<ApiResponse<Project>>(`/projects/${projectId}`, data)
  return response.data.data
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiClient.delete(`/projects/${projectId}`)
}

export interface ProjectSession {
  session_id: string
  title: string | null
  status: string
  latest_message: string | null
  created_at: string | null
  updated_at: string | null
}

export async function listProjectSessions(
  projectId: string,
  params?: { limit?: number; offset?: number },
): Promise<ProjectSession[]> {
  const response = await apiClient.get<ApiResponse<ProjectSession[]>>(
    `/projects/${projectId}/sessions`,
    { params },
  )
  return response.data.data
}
