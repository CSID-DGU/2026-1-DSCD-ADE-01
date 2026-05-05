import type { ChatbotOpenDetail } from "@/types/contract";

export const CHATBOT_OPEN_EVENT = "open-chatbot-panel";

export function openChatbotPanel(detail?: ChatbotOpenDetail) {
  window.dispatchEvent(
    new CustomEvent<ChatbotOpenDetail | undefined>(CHATBOT_OPEN_EVENT, { detail }),
  );
}
