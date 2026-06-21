"use client";

import { useQuery } from "@tanstack/react-query";
import api from "../api";
import type { SentimentValidationResponse } from "../types";

export function useSentimentValidation(days?: number) {
  return useQuery<SentimentValidationResponse>({
    queryKey: ["sentiment-validation", days],
    queryFn: () => api.getSentimentValidation(days),
  });
}
