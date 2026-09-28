import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': ['error', ...designRules()],
    },
  },
])

function designRules() {
  const arbitraryText = '/text-\\[\\d+(\\.\\d+)?px\\]/'
  const bareOutlineNone = '/^(?![\\s\\S]*ring)(?![\\s\\S]*outline-(?!none))[\\s\\S]*\\boutline-none\\b/'
  const heightClass = '/(?<![\\w-])h-\\d/'
  const arbitraryTextMessage =
    'Arbitrary font sizes are banned. Use the type scale (text-2xs is the 11px floor). See docs/UI.md#design-rules.'
  const outlineMessage =
    'outline-none needs a visible focus replacement (ring-* or outline-*) in the same class string. See docs/UI.md#design-rules.'
  const buttonHeightMessage =
    'Do not override Button height via className. Use the size prop (xs, sm, default, lg, icon, icon-sm). See docs/UI.md#design-rules.'
  return [
    { selector: `Literal[value=${arbitraryText}]`, message: arbitraryTextMessage },
    { selector: `TemplateElement[value.raw=${arbitraryText}]`, message: arbitraryTextMessage },
    { selector: `Literal[value=${bareOutlineNone}]`, message: outlineMessage },
    { selector: `TemplateElement[value.raw=${bareOutlineNone}]`, message: outlineMessage },
    {
      selector: `JSXOpeningElement[name.name='Button'] > JSXAttribute[name.name='className'] Literal[value=${heightClass}]`,
      message: buttonHeightMessage,
    },
    {
      selector: `JSXOpeningElement[name.name='Button'] > JSXAttribute[name.name='className'] TemplateElement[value.raw=${heightClass}]`,
      message: buttonHeightMessage,
    },
  ]
}
