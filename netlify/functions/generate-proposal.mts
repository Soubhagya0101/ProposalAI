import type { Config, Context } from "@netlify/functions";

const GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions";
const MODEL_ID = "openai/gpt-4o";

type Profile = {
  fullName?: string;
  niche?: string;
  experience?: string;
  tone?: string;
  skills?: string[];
  pastWin?: string;
  rate?: string;
};

type RequestBody = {
  profile?: Profile;
  jobDescription?: string;
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json"
    }
  });
}

function safeTrim(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function extractClientGreeting(jobDescription: string) {
  const patterns = [
    /\b(?:client|company|brand|business|organization)\s*(?:name\s*[:=-]?|is\s*|[:=-])\s*([A-Z][A-Za-z0-9&'. -]{1,60})/i,
    /\b(?:we are|we're)\s+([A-Z][A-Za-z0-9&'. -]{1,60})/i,
    /\bfor\s+([A-Z][A-Za-z0-9&'. -]{1,60})\b/
  ];

  for (const pattern of patterns) {
    const match = jobDescription.match(pattern);
    const candidate = match?.[1]
      ?.split(/[.\n,;|]/)[0]
      ?.split(/\b(?:and|is|that|who|which|needs?|looking|hiring|seeking|searching|building)\b/i)[0]
      ?.trim()
      .replace(/[.,;:!?]+$/, "");
    if (candidate && candidate.length <= 60 && !/\b(?:looking|hiring|seeking|need|searching|building)\b/i.test(candidate)) {
      return `Hi ${candidate}`;
    }
  }

  return "Hi there";
}

function removeBracketPlaceholders(text: string, greeting: string) {
  let cleaned = text
    .replace(/\[[^\]]+\]/g, "")
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/[ \t]{2,}/g, " ")
    .trim();

  const expectedStart = `${greeting},`;
  if (cleaned.toLowerCase().startsWith(expectedStart.toLowerCase())) {
    return cleaned;
  }

  const commaIndex = cleaned.indexOf(",");
  const firstCommaIsGreeting = commaIndex > -1 && commaIndex < 80 && /^(hi|hello|dear)\b/i.test(cleaned);
  if (firstCommaIsGreeting) {
    cleaned = cleaned.slice(commaIndex + 1).trim();
  }

  return `${expectedStart}\n\n${cleaned}`.trim();
}

function buildPrompt(profile: Required<Profile>, jobDescription: string, greeting: string) {
  return [
    "Write a ready-to-send freelance proposal for the job description below.",
    "",
    "Requirements:",
    `- Start exactly with: ${greeting},`,
    "- Never use bracket placeholders such as [Client's Name], [Your Name], or [Company].",
    "- If the client name is unclear, use exactly: Hi there,",
    "- 300 to 400 words. This is mandatory; target 330 to 370 words.",
    "- Use 5 to 7 short paragraphs, not bullets.",
    `- Tone: ${profile.tone}.`,
    "- Sound natural, specific, and human.",
    "- Reference the freelancer's skills and past win naturally, without forcing them.",
    "- Include the rate only if it feels appropriate and non-pushy.",
    "- End with a clear call to action.",
    "- Return only the proposal text. Do not include notes, markdown labels, or analysis.",
    "",
    "Freelancer profile:",
    `Name: ${profile.fullName}`,
    `Niche: ${profile.niche}`,
    `Experience: ${profile.experience} years`,
    `Top skills: ${profile.skills.join(", ")}`,
    `Past win: ${profile.pastWin}`,
    `Rate: ${profile.rate}`,
    "",
    "Job description:",
    jobDescription
  ].join("\n");
}

function wordCount(text: string) {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

async function requestProposal(githubToken: string, prompt: string, temperature = 0.7) {
  const githubResponse = await fetch(GITHUB_MODELS_URL, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${githubToken}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2026-03-10"
    },
    body: JSON.stringify({
      model: MODEL_ID,
      temperature,
      max_tokens: 1300,
      messages: [
        {
          role: "system",
          content: "You are an expert freelance proposal writer. You write credible, client-focused proposals that feel personal and specific. Follow requested word counts carefully."
        },
        {
          role: "user",
          content: prompt
        }
      ]
    })
  });

  const data = await githubResponse.json().catch(() => ({}));

  if (!githubResponse.ok) {
    const message = typeof data?.message === "string" ? data.message : "GitHub Models request failed.";
    return { error: message, status: githubResponse.status };
  }

  const proposal = data?.choices?.[0]?.message?.content;

  if (typeof proposal !== "string" || !proposal.trim()) {
    return { error: "GitHub Models returned an empty proposal.", status: 502 };
  }

  return { proposal: proposal.trim(), status: 200 };
}

function normalizeProfile(profile: Profile | undefined): Required<Profile> | null {
  if (!profile) {
    return null;
  }

  const normalized = {
    fullName: safeTrim(profile.fullName),
    niche: safeTrim(profile.niche),
    experience: safeTrim(profile.experience),
    tone: safeTrim(profile.tone) || "Professional",
    skills: Array.isArray(profile.skills) ? profile.skills.map(safeTrim).filter(Boolean).slice(0, 3) : [],
    pastWin: safeTrim(profile.pastWin),
    rate: safeTrim(profile.rate)
  };

  if (
    !normalized.fullName ||
    !normalized.niche ||
    !normalized.experience ||
    normalized.skills.length !== 3 ||
    !normalized.pastWin ||
    !normalized.rate
  ) {
    return null;
  }

  return normalized;
}

export default async (req: Request, _context: Context) => {
  if (req.method !== "POST") {
    return json({ error: "Method not allowed." }, 405);
  }

  let body: RequestBody;

  try {
    body = await req.json();
  } catch {
    return json({ error: "Invalid JSON request." }, 400);
  }

  const githubToken = Netlify.env.get("GITHUB_MODELS_TOKEN") || "";
  const profile = normalizeProfile(body.profile);
  const jobDescription = safeTrim(body.jobDescription);

  if (!githubToken) {
    return json({ error: "GitHub Models token is not configured on the server." }, 500);
  }

  if (!profile) {
    return json({ error: "Complete the freelancer profile first." }, 400);
  }

  if (!jobDescription) {
    return json({ error: "Paste a job description first." }, 400);
  }

  const greeting = extractClientGreeting(jobDescription);
  const prompt = buildPrompt(profile, jobDescription, greeting);
  let result = await requestProposal(githubToken, prompt);

  if (result.error || !result.proposal) {
    return json({ error: result.error }, result.status);
  }

  let proposal = removeBracketPlaceholders(result.proposal, greeting);
  let count = wordCount(proposal);

  for (let attempt = 0; attempt < 3 && (count < 300 || count > 400); attempt += 1) {
    const lengthInstruction = count < 300
      ? `The current proposal is ${count} words, which is too short. Expand it to 340 to 370 words by adding concrete understanding of the client's project, your working approach, expected collaboration steps, and a stronger call to action.`
      : `The current proposal is ${count} words, which is too long. Tighten it to 340 to 370 words while preserving specificity, credibility, and the call to action.`;

    result = await requestProposal(
      githubToken,
      [
        lengthInstruction,
        "The final answer must be 300 to 400 words. Do not use bullets.",
        "Keep it ready to send, natural, specific, and client-focused.",
        "Keep the same tone and call to action.",
        `Start exactly with: ${greeting},`,
        "Never include bracket placeholders.",
        "Return only the revised proposal text.",
        "",
        proposal
      ].join("\n"),
      0.35
    );

    if (result.error || !result.proposal) {
      return json({ error: result.error }, result.status);
    }

    proposal = removeBracketPlaceholders(result.proposal, greeting);
    count = wordCount(proposal);
  }

  return json({
    model: MODEL_ID,
    proposal: proposal.trim()
  });
};

export const config: Config = {
  path: "/api/generate-proposal"
};
