import type * as MonacoEditor from 'monaco-editor'

type Monaco = typeof MonacoEditor

export function registerJinja2Language(monaco: Monaco): void {
  monaco.languages.register({ id: 'jinja2-md' })

  monaco.languages.setMonarchTokensProvider('jinja2-md', {
    tokenizer: {
      root: [
        [/\{#/, 'comment', '@comment'],
        [/\{\{/, 'variable', '@expression'],
        [/\{%/, 'keyword', '@block'],
        [/^#{1,6}\s.*$/, 'keyword'],
        [/./, 'string'],
      ],
      comment: [
        [/#\}/, 'comment', '@pop'],
        [/./, 'comment'],
      ],
      expression: [
        [/\}\}/, 'variable', '@pop'],
        [/./, 'variable'],
      ],
      block: [
        [/%\}/, 'keyword', '@pop'],
        [/./, 'keyword'],
      ],
    },
  })
}
