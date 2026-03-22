import { describe, it, expect } from 'vitest'
import {
  listPromptsApiPromptsGet,
  getPromptApiPromptsPromptIdGet,
  createPromptApiPromptsPost,
  updateTemplateApiPromptsPromptIdTemplatePut,
  listCasesApiPromptsPromptIdDatasetGet,
  addCaseApiPromptsPromptIdDatasetPost,
  updateCaseApiPromptsPromptIdDatasetCaseIdPut,
  deleteCaseApiPromptsPromptIdDatasetCaseIdDelete,
  getCaseApiPromptsPromptIdDatasetCaseIdGet,
  importCasesApiPromptsPromptIdDatasetImportPost,
  startEvolutionApiEvolutionStartPost,
  stopEvolutionApiEvolutionRunIdStopPost,
  getRunStatusApiEvolutionRunIdStatusGet,
  getHistoryApiHistoryPromptIdGet,
  getRunDetailApiHistoryRunRunIdGet,
} from '../client/sdk.gen'

describe('Generated OpenAPI client', () => {
  it('exports prompt functions', () => {
    expect(typeof listPromptsApiPromptsGet).toBe('function')
    expect(typeof getPromptApiPromptsPromptIdGet).toBe('function')
    expect(typeof createPromptApiPromptsPost).toBe('function')
    expect(typeof updateTemplateApiPromptsPromptIdTemplatePut).toBe('function')
  })

  it('exports dataset functions', () => {
    expect(typeof listCasesApiPromptsPromptIdDatasetGet).toBe('function')
    expect(typeof addCaseApiPromptsPromptIdDatasetPost).toBe('function')
    expect(typeof updateCaseApiPromptsPromptIdDatasetCaseIdPut).toBe('function')
    expect(typeof deleteCaseApiPromptsPromptIdDatasetCaseIdDelete).toBe('function')
    expect(typeof getCaseApiPromptsPromptIdDatasetCaseIdGet).toBe('function')
    expect(typeof importCasesApiPromptsPromptIdDatasetImportPost).toBe('function')
  })

  it('exports evolution functions', () => {
    expect(typeof startEvolutionApiEvolutionStartPost).toBe('function')
    expect(typeof stopEvolutionApiEvolutionRunIdStopPost).toBe('function')
    expect(typeof getRunStatusApiEvolutionRunIdStatusGet).toBe('function')
  })

  it('exports history functions', () => {
    expect(typeof getHistoryApiHistoryPromptIdGet).toBe('function')
    expect(typeof getRunDetailApiHistoryRunRunIdGet).toBe('function')
  })
})
