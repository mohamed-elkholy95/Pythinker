import { Mark, markInputRule, markPasteRule } from '@tiptap/core'

export interface SlashCommandOptions {
  HTMLAttributes: Record<string, unknown>
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    slashCommand: {
      setSlashCommand: () => ReturnType
      toggleSlashCommand: () => ReturnType
      unsetSlashCommand: () => ReturnType
    }
  }
}

// Input rule: when user types a slash command
const inputRegex = /(\/[a-zA-Z][a-zA-Z0-9-]*)$/

// Paste rule: when user pastes text containing slash commands
const pasteRegex = /(\/[a-zA-Z][a-zA-Z0-9-]*)/g

export const SlashCommand = Mark.create<SlashCommandOptions>({
  name: 'slashCommand',

  addOptions() {
    return {
      HTMLAttributes: {},
    }
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-slash-command]',
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      {
        ...this.options.HTMLAttributes,
        ...HTMLAttributes,
        'data-slash-command': '',
        class: 'slash-command',
      },
      0,
    ]
  },

  addCommands() {
    return {
      setSlashCommand:
        () =>
        ({ commands }) => {
          return commands.setMark(this.name)
        },
      toggleSlashCommand:
        () =>
        ({ commands }) => {
          return commands.toggleMark(this.name)
        },
      unsetSlashCommand:
        () =>
        ({ commands }) => {
          return commands.unsetMark(this.name)
        },
    }
  },

  addInputRules() {
    return [
      markInputRule({
        find: inputRegex,
        type: this.type,
      }),
    ]
  },

  addPasteRules() {
    return [
      markPasteRule({
        find: pasteRegex,
        type: this.type,
      }),
    ]
  },
})

export default SlashCommand
