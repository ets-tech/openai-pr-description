#!/usr/bin/env python3
import sys
import requests
import argparse
import json
import openai
import os

SAMPLE_PROMPT = """
Act as developer with years of industrial work experience in application developement along with good knowledge of git and development strategies.

Your mission is to write a pull request description focusing on the motivation behind the change and why it improves the project along with GitMoji convention.

Also you need to create clean, single and comprehensive commit messages in the conventional commit convention and explain why a change was done in the generated message. The commit message should follow git commit message standards along with GitMoji convention. Don\'t start it with "This commit", just describe the changes. Use the present tense.

Go straight to the point.

For your context the title of the pull request is "Enable valgrind on CI" and the following changes took place: 

Changes in file .github/workflows/build-ut-coverage.yml: @@ -24,6 +24,7 @@ jobs:
         run: |
           sudo apt-get update
           sudo apt-get install -y lcov
+          sudo apt-get install -y valgrind
           sudo apt-get install -y ${{ matrix.compiler.cc }}
           sudo apt-get install -y ${{ matrix.compiler.cxx }}
       - name: Checkout repository
@@ -48,3 +49,7 @@ jobs:
         with:
           files: coverage.info
           fail_ci_if_error: true
+      - name: Run valgrind
+        run: |
+          valgrind --tool=memcheck --leak-check=full --leak-resolution=med \
+            --track-origins=yes --vgdb=no --error-exitcode=1 ${build_dir}/test/command_parser_test
Changes in file test/CommandParserTest.cpp: @@ -566,7 +566,7 @@ TEST(CommandParserTest, ParsedCommandImpl_WhenArgumentIsSupportedNumericTypeWill
     unsigned long long expectedUnsignedLongLong { std::numeric_limits<unsigned long long>::max() };
     float expectedFloat { -164223.123f }; // std::to_string does not play well with floating point min()
     double expectedDouble { std::numeric_limits<double>::max() };
-    long double expectedLongDouble { std::numeric_limits<long double>::max() };
+    long double expectedLongDouble { 123455678912349.1245678912349L };
 
     auto command = UnparsedCommand::create(expectedCommand, "dummyDescription"s)
                        .withArgs<int, long, unsigned long, long long, unsigned long long, float, double, long double>();
"""

GOOD_SAMPLE_RESPONSE = """
🚀 **Title: Enable valgrind on CI**

**Motivation:**
This pull request introduces the use of Valgrind in our CI pipeline, specifically within the build-ut-coverage.yml workflow. Valgrind is a crucial tool for memory debugging, memory leak detection, and profiling. Integrating it ensures that every commit is checked for memory leaks and errors, significantly improving code quality and reliability.

**Changes:**
1. In `.github/workflows/build-ut-coverage.yml`, added commands to install Valgrind in the CI environment.
2. Implemented a step to run Valgrind with our test suite, ensuring any memory issues are caught automatically.

**Improvement:**
By enabling Valgrind on CI, we're proactively preventing memory leaks and other related issues from being merged into the main code base. This enhancement aligns with our commitment to quality and reliability in our software development process.

**Commit message:**
🧪 feat: Add Valgrind for Memory Leak Checks in Build Workflow

- Add Valgrind installation in the build-ut-coverage.yml to enhance the CI pipeline by including memory leak checks. This ensures robustness in the build process by identifying potential memory leaks early.
- Modify a test case in test/CommandParserTest.cpp, updating the `expectedLongDouble` value to a more precise and large decimal number. This change improves the test coverage and accuracy for testing floating-point operations.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Use ChatGPT to generate a description for a pull request."
    )
    parser.add_argument(
        "--github-api-url", type=str, required=True, help="The GitHub API URL"
    )
    parser.add_argument(
        "--github-repository", type=str, required=True, help="The GitHub repository"
    )
    parser.add_argument(
        "--pull-request-id",
        type=int,
        required=True,
        help="The pull request ID",
    )
    parser.add_argument(
        "--github-token",
        type=str,
        required=True,
        help="The GitHub token",
    )
    parser.add_argument(
        "--openai-api-key",
        type=str,
        required=True,
        help="The OpenAI API key",
    )
    parser.add_argument(
        "--allowed-users",
        type=str,
        required=False,
        help="A comma-separated list of GitHub usernames that are allowed to trigger the action, empty or missing means all users are allowed",
    )
    parser.add_argument(
        "--overwrite-existing-description",
        type=bool,
        required=False,
        help="Whether to overwrite an existing pull request description",
    )
    args = parser.parse_args()

    github_api_url = args.github_api_url
    repo = args.github_repository
    github_token = args.github_token
    pull_request_id = args.pull_request_id
    openai_api_key = args.openai_api_key
    allowed_users = os.environ.get("INPUT_ALLOWED_USERS", "")
    if allowed_users:
        allowed_users = allowed_users.split(",")
    open_ai_model = os.environ.get("INPUT_OPENAI_MODEL", "gpt-3.5-turbo")
    max_prompt_tokens = int(os.environ.get("INPUT_MAX_TOKENS", "1000"))
    model_temperature = float(os.environ.get("INPUT_TEMPERATURE", "0.6"))
    model_sample_prompt = os.environ.get("INPUT_MODEL_SAMPLE_PROMPT", SAMPLE_PROMPT)
    model_sample_response = os.environ.get(
        "INPUT_MODEL_SAMPLE_RESPONSE", GOOD_SAMPLE_RESPONSE
    )
    overwrite_existing_description = os.environ.get(
        "INPUT_OVERWRITE_EXISTING_DESCRIPTION", "false"
    )
    authorization_header = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": "token %s" % github_token,
    }

    pull_request_url = f"{github_api_url}/repos/{repo}/pulls/{pull_request_id}"
    pull_request_result = requests.get(
        pull_request_url,
        headers=authorization_header,
    )
    if pull_request_result.status_code != requests.codes.ok:
        print(
            "Request to get pull request data failed: "
            + str(pull_request_result.status_code)
        )
        return 1
    pull_request_data = json.loads(pull_request_result.text)

    if pull_request_data["body"] and overwrite_existing_description == "false":
        print("Pull request already has a description, skipping")
        return 0

    if allowed_users:
        pr_author = pull_request_data["user"]["login"]
        if pr_author not in allowed_users:
            print(
                f"Pull request author {pr_author} is not allowed to trigger this action"
            )
            return 0

    pull_request_title = pull_request_data["title"]
    pull_request_description = pull_request_data["body"]

    pull_request_files = []
    # Request a maximum of 10 pages (300 files)
    for page_num in range(1, 11):
        pull_files_url = f"{pull_request_url}/files?page={page_num}&per_page=30"
        pull_files_result = requests.get(
            pull_files_url,
            headers=authorization_header,
        )

        if pull_files_result.status_code != requests.codes.ok:
            print(
                "Request to get list of files failed with error code: "
                + str(pull_files_result.status_code)
            )
            return 1

        pull_files_chunk = json.loads(pull_files_result.text)

        if len(pull_files_chunk) == 0:
            break

        pull_request_files.extend(pull_files_chunk)

        completion_prompt = f"""
Act as developer with years of industrial work experience in application developement along with good knowledge of git and development strategies.

Your mission is to write a pull request description focusing on the motivation behind the change and why it improves the project along with GitMoji convention.

Also you need to create clean, single and comprehensive commit messages in the conventional commit convention and explain why a change was done in the generated message. The commit message should follow git commit message standards along with GitMoji convention. Don\'t start it with "This commit", just describe the changes. Use the present tense.

Go straight to the point.

For your context the title of the pull request is "{pull_request_title}" and pull request description is "{pull_request_description}". The following changes took place: \n
"""
    for pull_request_file in pull_request_files:
        # Not all PR file metadata entries may contain a patch section
        # For example, entries related to removed binary files may not contain it
        if "patch" not in pull_request_file:
            continue

        filename = pull_request_file["filename"]
        patch = pull_request_file["patch"]
        completion_prompt += f"Changes in file {filename}: {patch}\n"

    max_allowed_tokens = 2048  # 4096 is the maximum allowed by OpenAI for GPT-3.5
    characters_per_token = 4  # The average number of characters per token
    max_allowed_characters = max_allowed_tokens * characters_per_token
    if len(completion_prompt) > max_allowed_characters:
        completion_prompt = completion_prompt[:max_allowed_characters]

    openai.api_key = openai_api_key
    openai_response = openai.ChatCompletion.create(
        model=open_ai_model,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant who writes pull request descriptions",
            },
            {"role": "user", "content": model_sample_prompt},
            {"role": "assistant", "content": model_sample_response},
            {"role": "user", "content": completion_prompt},
        ],
        temperature=model_temperature,
        max_tokens=max_prompt_tokens,
    )

    generated_pr_description = openai_response.choices[0].message.content
    redundant_prefix = "This pull request "
    if generated_pr_description.startswith(redundant_prefix):
        generated_pr_description = generated_pr_description[len(redundant_prefix) :]
        generated_pr_description = (
            generated_pr_description[0].upper() + generated_pr_description[1:]
        )
    print(f"Generated pull request description: '{generated_pr_description}'")
    issues_url = "%s/repos/%s/issues/%s" % (
        github_api_url,
        repo,
        pull_request_id,
    )
    update_pr_description_result = requests.patch(
        issues_url,
        headers=authorization_header,
        json={"body": generated_pr_description},
    )

    if update_pr_description_result.status_code != requests.codes.ok:
        print(
            "Request to update pull request description failed: "
            + str(update_pr_description_result.status_code)
        )
        print("Response: " + update_pr_description_result.text)
        return 1


if __name__ == "__main__":
    sys.exit(main())
