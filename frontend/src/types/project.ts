export interface Project {
  id: string
  name: string
  instructions: string
  connector_ids: string[]
  file_ids: string[]
  skill_ids: string[]
  status: 'active' | 'archived'
  session_count: number
  created_at: string
  updated_at: string
}

export interface CreateProjectRequest {
  name: string
  instructions?: string
  connector_ids?: string[]
}

export interface UpdateProjectRequest {
  name?: string
  instructions?: string
  connector_ids?: string[]
  file_ids?: string[]
  skill_ids?: string[]
  status?: 'active' | 'archived'
}

export interface ProjectListItem {
  id: string
  name: string
  status: 'active' | 'archived'
  session_count: number
  updated_at: string
}
