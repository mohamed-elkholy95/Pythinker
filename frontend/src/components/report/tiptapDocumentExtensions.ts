import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Highlight from '@tiptap/extension-highlight';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import TextAlign from '@tiptap/extension-text-align';
import Typography from '@tiptap/extension-typography';
import Underline from '@tiptap/extension-underline';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import { TextStyle } from '@tiptap/extension-text-style';
import Color from '@tiptap/extension-color';
import Superscript from '@tiptap/extension-superscript';
import Subscript from '@tiptap/extension-subscript';
import { common, createLowlight } from 'lowlight';
import { PlotlyChartBlock } from './tiptapPlotlyExtension';

const lowlight = createLowlight(common);

export const createTiptapDocumentExtensions = () => [
  // PlotlyChartBlock must come before CodeBlockLowlight so its parseHTML
  // rule takes precedence for `language-chart` / `language-plotly` code fences.
  PlotlyChartBlock,
  StarterKit.configure({
    codeBlock: false,
    link: false,
    underline: false,
  }),
  Link.configure({
    openOnClick: true,
    HTMLAttributes: {
      class: 'report-link hover:underline cursor-pointer',
      target: '_blank',
      rel: 'noopener noreferrer',
    },
  }),
  Image.configure({
    HTMLAttributes: {
      class: 'max-w-full h-auto rounded-lg my-4',
    },
  }),
  Highlight.configure({
    multicolor: true,
  }),
  TaskList,
  TaskItem.configure({
    nested: true,
  }),
  TextAlign.configure({
    types: ['heading', 'paragraph'],
  }),
  Typography,
  Underline,
  TextStyle,
  Color.configure({
    types: [TextStyle.name],
  }),
  Superscript,
  Subscript,
  Table.configure({
    resizable: false,
    HTMLAttributes: {
      class: 'tiptap-table',
    },
  }),
  TableRow,
  TableHeader,
  TableCell,
  CodeBlockLowlight.configure({
    lowlight,
    HTMLAttributes: {
      class: 'bg-[var(--fill-tsp-gray-main)] rounded-lg p-4 my-4 overflow-x-auto text-sm font-mono',
    },
  }),
];
