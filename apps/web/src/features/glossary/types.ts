export const GLOSSARY_RULE_TYPES = [
  "KEEP_ORIGINAL",
  "TRANSLATE_AS",
  "ORIGINAL_THEN_TRANSLATION",
  "TRANSLATION_THEN_ORIGINAL",
  "PRESERVE_ABBREVIATION",
  "IGNORE",
] as const;

export type GlossaryRuleType = (typeof GLOSSARY_RULE_TYPES)[number];

export const GLOSSARY_SCOPES = [
  "SYSTEM",
  "DOMAIN",
  "USER",
  "PROJECT",
  "DOCUMENT",
  "SECTION",
  "PAGE",
  "SEGMENT",
] as const;

export type GlossaryScope = (typeof GLOSSARY_SCOPES)[number];

export interface GlossaryTerm {
  id: string;
  sourceTerm: string;
  targetTerm: string | null;
  ruleType: GlossaryRuleType;
  scope: GlossaryScope;
  priority: number;
  caseSensitive: boolean;
  wholeWord: boolean;
  currentRevision: number;
  occurrenceCount: number;
}

export interface SaveGlossaryTermInput {
  sourceTerm: string;
  targetTerm: string | null;
  ruleType: GlossaryRuleType;
  scope: GlossaryScope;
  priority: number;
  caseSensitive: boolean;
  wholeWord: boolean;
}

export interface UpdateGlossaryTermInput extends SaveGlossaryTermInput {
  expectedRevision: number;
}

export interface GlossaryCandidate {
  id: string;
  sourceTerm: string;
  occurrenceCount: number;
  confidence: number;
  candidateType: string;
}

export interface AcceptGlossaryCandidateInput {
  glossaryId: string;
  ruleType: GlossaryRuleType;
  targetTerm: string | null;
  scope: GlossaryScope;
}

export interface GlossaryConflict {
  id: string;
  sourceTerm: string;
  conflictType: string;
  explanation: string;
  blocking: boolean;
}

export interface GlossaryOccurrence {
  id: string;
  segmentId: string;
  pageId: string;
  matchedText: string;
  sourceContext: string;
  finalTranslation: string | null;
}

export interface GlossaryUiClient {
  listTerms(this: void, glossaryId: string): Promise<readonly GlossaryTerm[]>;
  createTerm(
    this: void,
    glossaryId: string,
    input: SaveGlossaryTermInput,
  ): Promise<GlossaryTerm>;
  updateTerm(
    this: void,
    termId: string,
    input: UpdateGlossaryTermInput,
  ): Promise<GlossaryTerm>;
  deactivateTerm(this: void, termId: string): Promise<void>;
  listCandidates(this: void, projectId: string): Promise<readonly GlossaryCandidate[]>;
  acceptCandidate(
    this: void,
    candidateId: string,
    input: AcceptGlossaryCandidateInput,
  ): Promise<void>;
  rejectCandidate(this: void, candidateId: string, reason: string): Promise<void>;
  listConflicts(this: void, projectId: string): Promise<readonly GlossaryConflict[]>;
  listOccurrences(this: void, termId: string): Promise<readonly GlossaryOccurrence[]>;
}
