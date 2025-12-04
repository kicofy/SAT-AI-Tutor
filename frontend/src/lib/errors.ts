type ErrorLike = {
  response?: {
    data?: {
      message?: string;
    };
  };
};

function hasMessage(error: unknown): error is ErrorLike {
  return (
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    typeof (error as ErrorLike).response?.data?.message === "string"
  );
}

export function extractErrorMessage(error: unknown, fallback: string) {
  if (hasMessage(error) && error.response?.data?.message) {
    return error.response.data.message;
  }
  return fallback;
}

