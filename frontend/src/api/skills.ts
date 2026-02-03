import { apiClient } from './client';

// Skill type definitions
export interface Skill {
  id: string;
  name: string;
  description: string;
  category: string;
  source: 'official' | 'community' | 'custom';
  icon: string;
  required_tools: string[];
  optional_tools: string[];
  is_premium: boolean;
  default_enabled: boolean;
  version: string;
  author: string | null;
  updated_at: string;
  // Custom skill fields
  owner_id?: string | null;
  is_public?: boolean;
  parent_skill_id?: string | null;
  system_prompt_addition?: string | null;
  // Claude-style configuration fields
  invocation_type?: 'user' | 'ai' | 'both';
  allowed_tools?: string[] | null;
  supports_dynamic_context?: boolean;
  trigger_patterns?: string[];
}

export interface UserSkill {
  skill: Skill;
  enabled: boolean;
  config: Record<string, unknown>;
  order: number;
}

export interface SkillListResponse {
  skills: Skill[];
  total: number;
}

export interface UserSkillsResponse {
  skills: UserSkill[];
  enabled_count: number;
  max_skills: number;
}

export interface UpdateUserSkillRequest {
  enabled?: boolean;
  config?: Record<string, unknown>;
  order?: number;
}

export interface SkillToolsResponse {
  skill_ids: string[];
  tools: string[];
}

/**
 * Get all available skills
 */
export async function getAvailableSkills(category?: string): Promise<Skill[]> {
  const params = category ? { category } : undefined;
  const response = await apiClient.get<{ data: SkillListResponse }>('/skills', { params });
  return response.data.data.skills;
}

/**
 * Get a specific skill by ID
 */
export async function getSkillById(skillId: string): Promise<Skill> {
  const response = await apiClient.get<{ data: Skill }>(`/skills/${skillId}`);
  return response.data.data;
}

/**
 * Get current user's skill configurations
 */
export async function getUserSkills(): Promise<UserSkillsResponse> {
  const response = await apiClient.get<{ data: UserSkillsResponse }>('/skills/user/config');
  return response.data.data;
}

/**
 * Update a user's skill configuration (enable/disable or configure)
 */
export async function updateUserSkill(
  skillId: string,
  data: UpdateUserSkillRequest
): Promise<UserSkill> {
  const response = await apiClient.put<{ data: UserSkill }>(`/skills/user/${skillId}`, data);
  return response.data.data;
}

/**
 * Enable multiple skills at once (replaces current enabled skills)
 */
export async function enableSkills(skillIds: string[]): Promise<UserSkillsResponse> {
  const response = await apiClient.post<{ data: UserSkillsResponse }>(
    '/skills/user/enable',
    { skill_ids: skillIds }
  );
  return response.data.data;
}

/**
 * Get tools required by specific skills
 */
export async function getSkillTools(skillIds: string[]): Promise<SkillToolsResponse> {
  const params = { skill_ids: skillIds.join(',') };
  const response = await apiClient.get<{ data: SkillToolsResponse }>('/skills/tools/required', {
    params,
  });
  return response.data.data;
}

// Skill category enum for frontend use
export const SKILL_CATEGORIES = {
  research: 'Research',
  coding: 'Coding',
  browser: 'Browser',
  file_management: 'File Management',
  data_analysis: 'Data Analysis',
  communication: 'Communication',
  custom: 'Custom',
} as const;

// Maximum skills allowed to be enabled at once
export const MAX_ENABLED_SKILLS = 5;

// Custom Skill CRUD Types
export interface CreateCustomSkillRequest {
  name: string;
  description: string;
  category?: string;
  icon?: string;
  required_tools: string[];
  optional_tools?: string[];
  system_prompt_addition: string;
  // Claude-style configuration (optional)
  invocation_type?: 'user' | 'ai' | 'both';
  allowed_tools?: string[];
  supports_dynamic_context?: boolean;
  trigger_patterns?: string[];
}

export interface UpdateCustomSkillRequest {
  name?: string;
  description?: string;
  icon?: string;
  required_tools?: string[];
  optional_tools?: string[];
  system_prompt_addition?: string;
  // Claude-style configuration updates
  invocation_type?: 'user' | 'ai' | 'both';
  allowed_tools?: string[] | null;
  supports_dynamic_context?: boolean;
  trigger_patterns?: string[];
}

export interface CustomSkillListResponse {
  skills: Skill[];
  total: number;
}

// Custom Skill CRUD Functions

/**
 * Create a new custom skill
 */
export async function createCustomSkill(data: CreateCustomSkillRequest): Promise<Skill> {
  const response = await apiClient.post<{ data: Skill }>('/skills/custom', data);
  return response.data.data;
}

/**
 * Get all custom skills owned by the current user
 */
export async function getMyCustomSkills(): Promise<Skill[]> {
  const response = await apiClient.get<{ data: CustomSkillListResponse }>('/skills/custom');
  return response.data.data.skills;
}

/**
 * Get a specific custom skill by ID
 */
export async function getCustomSkillById(skillId: string): Promise<Skill> {
  const response = await apiClient.get<{ data: Skill }>(`/skills/custom/${skillId}`);
  return response.data.data;
}

/**
 * Update a custom skill
 */
export async function updateCustomSkill(
  skillId: string,
  data: UpdateCustomSkillRequest
): Promise<Skill> {
  const response = await apiClient.put<{ data: Skill }>(`/skills/custom/${skillId}`, data);
  return response.data.data;
}

/**
 * Delete a custom skill
 */
export async function deleteCustomSkill(skillId: string): Promise<void> {
  await apiClient.delete(`/skills/custom/${skillId}`);
}

/**
 * Publish a custom skill to the community
 */
export async function publishCustomSkill(skillId: string): Promise<Skill> {
  const response = await apiClient.post<{ data: Skill }>(`/skills/custom/${skillId}/publish`, {
    confirm: true,
  });
  return response.data.data;
}

// =============================================================================
// SKILL PACKAGE OPERATIONS (for skill delivery)
// =============================================================================

export interface SkillPackageFile {
  path: string;
  content: string;
  size: number;
}

export interface SkillPackageResponse {
  id: string;
  name: string;
  description: string;
  version: string;
  icon: string;
  category: string;
  author?: string;
  file_tree: Record<string, unknown>;
  files: SkillPackageFile[];
  file_id?: string;
  skill_id?: string;
  file_count: number;
  created_at?: string;
}

/**
 * Get a skill package by ID
 */
export async function getSkillPackage(packageId: string): Promise<SkillPackageResponse> {
  const response = await apiClient.get<{ data: SkillPackageResponse }>(
    `/skills/packages/${packageId}`
  );
  return response.data.data;
}

/**
 * Download a skill package as a .skill ZIP file
 */
export async function downloadSkillPackage(packageId: string): Promise<void> {
  const response = await apiClient.get(`/skills/packages/${packageId}/download`, {
    responseType: 'blob',
  });

  // Get filename from Content-Disposition header or use default
  const contentDisposition = response.headers['content-disposition'];
  let filename = 'skill.skill';
  if (contentDisposition) {
    const match = contentDisposition.match(/filename="(.+)"/);
    if (match) {
      filename = match[1];
    }
  }

  // Create blob URL and trigger download
  const blob = response.data as Blob;
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

/**
 * Get a single file from a skill package
 */
export async function getSkillPackageFile(
  packageId: string,
  path: string
): Promise<SkillPackageFile> {
  const response = await apiClient.get<{ data: SkillPackageFile }>(
    `/skills/packages/${packageId}/file`,
    { params: { path } }
  );
  return response.data.data;
}

/**
 * Install a skill from a package
 */
export async function installSkillFromPackage(
  packageId: string,
  enableAfterInstall = true
): Promise<Skill> {
  const response = await apiClient.post<{ data: Skill }>(
    `/skills/packages/${packageId}/install`,
    { enable_after_install: enableAfterInstall }
  );
  return response.data.data;
}
