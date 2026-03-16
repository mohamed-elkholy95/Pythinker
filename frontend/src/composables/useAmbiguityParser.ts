import { computed, type Ref } from 'vue'

export interface AmbiguityResult {
  cleanedContent: string
  chips: string[]
}

const AMBIGUITY_TRIGGERS = [
  'did you mean',
  'could you clarify',
  'which of these',
  'please choose',
  'which option',
  'would you like to'
]

export function useAmbiguityParser(contentRef: Ref<string>) {
  return computed<AmbiguityResult>(() => {
    const text = contentRef.value || ''
    
    // Quick bailout if no list markers found near the end of the text
    if (!text.includes('- ') && !text.includes('* ') && !/\d+\.\s/.test(text)) {
      return { cleanedContent: text, chips: [] }
    }

    // Convert text to lowercase for trigger matching
    const lowerText = text.toLowerCase()
    
    // Find the last occurrence of any trigger phrase
    let lastTriggerIndex = -1
    for (const trigger of AMBIGUITY_TRIGGERS) {
      const idx = lowerText.lastIndexOf(trigger)
      if (idx > lastTriggerIndex) {
        lastTriggerIndex = idx
      }
    }

    // If no trigger found, return original text
    if (lastTriggerIndex === -1) {
      return { cleanedContent: text, chips: [] }
    }

    // Keep text up to the trigger point
    const prefix = text.substring(0, lastTriggerIndex)
    const suffix = text.substring(lastTriggerIndex)

    // Parse the suffix for list items
    const listRegex = /^(?:-|\*|\d+\.)\s+(.+)$/gm
    const chips: string[] = []
    let match
    
    while ((match = listRegex.exec(suffix)) !== null) {
      let optionText = match[1].trim()
      // Remove trailing punctuation or markdown bold/italic surrounding the option
      optionText = optionText.replace(/\.$/, '').replace(/\*\*([^*]+)\*\*/g, '$1').replace(/__([^_]+)__/g, '$1')
      if (optionText) {
        chips.push(optionText)
      }
    }

    // If we found chips, strip the suffix from the content except for the leading text (e.g. "Did you mean:")
    if (chips.length > 0) {
      const preListText = suffix.split(/(?:-|\*|\d+\.)\s+/)[0]?.trim() || ''
      const cleanedContent = prefix + preListText
      return { cleanedContent, chips }
    }

    return { cleanedContent: text, chips: [] }
  })
}
