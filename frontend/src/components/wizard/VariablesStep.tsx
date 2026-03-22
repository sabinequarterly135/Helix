import { useTranslation } from 'react-i18next'
import { Plus, X } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { WizardData, WizardVariable } from './WizardFlow'

interface VariablesStepProps {
  data: WizardData
  onChange: (data: WizardData) => void
}

const EMPTY_VARIABLE: WizardVariable = {
  name: '',
  varType: 'string',
  description: '',
  isAnchor: false,
  itemsSchema: undefined,
}

export function VariablesStep({ data, onChange }: VariablesStepProps) {
  const { t } = useTranslation()
  const updateVariable = (index: number, updated: Partial<WizardVariable>) => {
    const variables = data.variables.map((v, i) =>
      i === index ? { ...v, ...updated } : v
    )
    onChange({ ...data, variables })
  }

  const addVariable = () => {
    onChange({ ...data, variables: [...data.variables, { ...EMPTY_VARIABLE }] })
  }

  const removeVariable = (index: number) => {
    onChange({ ...data, variables: data.variables.filter((_, i) => i !== index) })
  }

  const updateSubField = (varIndex: number, subIndex: number, updated: Partial<WizardVariable>) => {
    const variable = data.variables[varIndex]
    const newSubFields = (variable.itemsSchema || []).map((sf, i) =>
      i === subIndex ? { ...sf, ...updated } : sf
    )
    updateVariable(varIndex, { itemsSchema: newSubFields })
  }

  const addSubField = (varIndex: number) => {
    const variable = data.variables[varIndex]
    const newSubFields = [...(variable.itemsSchema || []), { name: '', varType: 'string', description: '', isAnchor: false }]
    updateVariable(varIndex, { itemsSchema: newSubFields })
  }

  const removeSubField = (varIndex: number, subIndex: number) => {
    const variable = data.variables[varIndex]
    const newSubFields = (variable.itemsSchema || []).filter((_, i) => i !== subIndex)
    updateVariable(varIndex, { itemsSchema: newSubFields })
  }

  const handleTypeChange = (index: number, value: string) => {
    // Clear itemsSchema when switching away from object/array
    if (value !== 'object' && value !== 'array') {
      updateVariable(index, { varType: value, itemsSchema: undefined })
    } else {
      updateVariable(index, { varType: value })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{t('wizard.variables')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {t('wizard.variablesDescription')}
        </p>

        {data.variables.map((variable, index) => (
          <div
            key={index}
            className="flex flex-col gap-3 rounded-md border border-border p-4"
          >
            <div className="flex items-start gap-3">
              <div className="flex-1 space-y-2">
                <label className="text-sm font-medium text-foreground">Name</label>
                <Input
                  placeholder="e.g., customer_name"
                  value={variable.name}
                  onChange={(e) => updateVariable(index, { name: e.target.value })}
                />
              </div>
              <div className="w-32 space-y-2">
                <label className="text-sm font-medium text-foreground">Type</label>
                <Select
                  value={variable.varType}
                  onValueChange={(value) => handleTypeChange(index, value)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="string">string</SelectItem>
                    <SelectItem value="number">number</SelectItem>
                    <SelectItem value="boolean">boolean</SelectItem>
                    <SelectItem value="object">object</SelectItem>
                    <SelectItem value="array">array</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="mt-7 shrink-0"
                onClick={() => removeVariable(index)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Description</label>
              <Input
                placeholder="What this variable represents..."
                value={variable.description}
                onChange={(e) => updateVariable(index, { description: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">
                Examples
                <span className="ml-1 text-xs text-muted-foreground font-normal">
                  (optional - helps synthesis generate realistic values)
                </span>
              </label>
              <Textarea
                placeholder={
                  variable.varType === 'object' || variable.varType === 'array'
                    ? 'JSON examples, one per line:\n{"name": "Widget A", "price": 9.99}\n{"name": "Widget B", "price": 19.99}'
                    : 'Comma-separated values: Alice, Bob, Charlie'
                }
                value={variable.examples || ''}
                onChange={(e) => updateVariable(index, { examples: e.target.value })}
                rows={2}
                className="text-sm"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={variable.isAnchor}
                onChange={(e) => updateVariable(index, { isAnchor: e.target.checked })}
                className="rounded border-input"
              />
              <span className="text-foreground">Anchor variable</span>
              <span className="text-muted-foreground">(preserved during evolution)</span>
            </label>

            {/* Sub-field editor for object and array types */}
            {(variable.varType === 'object' || variable.varType === 'array') && (
              <div className="ml-6 mt-3 border-l-2 border-primary/20 pl-4 space-y-3">
                <div>
                  <span className="text-sm font-medium text-foreground">Sub-fields</span>
                  <p className="text-xs text-muted-foreground">
                    Define the fields for each {variable.varType === 'array' ? 'array element' : 'object'}
                  </p>
                </div>

                {(variable.itemsSchema || []).map((subField, subIndex) => (
                  <div
                    key={subIndex}
                    className="flex flex-col gap-2 rounded-md border border-border/60 bg-muted/30 p-3"
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex-1 space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">Name</label>
                        <Input
                          placeholder="e.g., field_name"
                          value={subField.name}
                          onChange={(e) => updateSubField(index, subIndex, { name: e.target.value })}
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="w-28 space-y-1">
                        <label className="text-xs font-medium text-muted-foreground">Type</label>
                        <Select
                          value={subField.varType}
                          onValueChange={(value) => updateSubField(index, subIndex, { varType: value })}
                        >
                          <SelectTrigger className="h-8 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="string">string</SelectItem>
                            <SelectItem value="number">number</SelectItem>
                            <SelectItem value="boolean">boolean</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="mt-5 h-8 w-8 shrink-0"
                        onClick={() => removeSubField(index, subIndex)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-muted-foreground">Description</label>
                      <Input
                        placeholder="What this field represents..."
                        value={subField.description}
                        onChange={(e) => updateSubField(index, subIndex, { description: e.target.value })}
                        className="h-8 text-sm"
                      />
                    </div>
                    {!variable.isAnchor && (
                      <label className="flex items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          checked={subField.isAnchor}
                          onChange={(e) => updateSubField(index, subIndex, { isAnchor: e.target.checked })}
                          className="rounded border-input"
                        />
                        <span className="text-foreground">Anchor</span>
                        <span className="text-muted-foreground">(preserved during evolution)</span>
                      </label>
                    )}
                  </div>
                ))}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => addSubField(index)}
                  className="w-full"
                >
                  <Plus className="h-3 w-3 mr-1" />
                  Add Sub-field
                </Button>
              </div>
            )}
          </div>
        ))}

        <Button variant="outline" onClick={addVariable} className="w-full">
          <Plus className="h-4 w-4 mr-2" />
          {t('wizard.addVariable')}
        </Button>
      </CardContent>
    </Card>
  )
}
