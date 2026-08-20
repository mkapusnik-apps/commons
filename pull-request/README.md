# Create or Update Pull Request

Creates a pull request for a given head/base pair, or updates the existing open pull request for the same pair.

## Multi-line body example

The `body`, `title`, `head`, and `base` inputs are passed to the action as runtime data. Callers do not need JavaScript-string escaping workarounds for Markdown bodies that include multiple lines, quotes, apostrophes, backticks, or code fences.

````yaml
- uses: mkapusnik-apps/commons/pull-request@v1
  with:
    head: release/promote-candidate
    base: master
    title: "Promote candidate: don't escape `inline code`"
    body: |
      ## Summary

      This body includes "double quotes", apostrophes like don't, and `inline code`.

      ```js
      const message = `Template literals and backticks are safe`;
      console.log(message);
      ```
    token: ${{ secrets.GITHUB_TOKEN }}
````
