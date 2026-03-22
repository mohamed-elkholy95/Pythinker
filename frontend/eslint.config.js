import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import vueTsEslintConfig from '@vue/eslint-config-typescript';

export default [
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  {
    name: 'app/files-to-ignore',
    ignores: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/node_modules/**'],
  },

  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  ...vueTsEslintConfig(),

  {
    name: 'app/custom-rules',
    rules: {
      // Allow unused variables that start with underscore
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_'
      }],
      // Warn on explicit any — migrate incrementally to proper types
      '@typescript-eslint/no-explicit-any': 'warn',
      // Allow empty object types in certain contexts
      '@typescript-eslint/no-empty-object-type': 'off',
      // Vue specific
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off',
      // Console statements - allow in development
      'no-console': 'off',
      'no-debugger': 'error',
    }
  }
];
