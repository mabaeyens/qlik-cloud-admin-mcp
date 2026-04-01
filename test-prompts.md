# Natural Language Test Prompts for Claude Desktop

Use these prompts verbatim (or close to it) in Claude Desktop to exercise the MCP tools.
They are grouped by entity and HTTP method, roughly ordered from read-only to destructive.

---

## Apps

**List all apps**
> List all apps available in my Qlik Cloud tenant.

**Find an app by name**
> Find the app called "Sales Overview" and show me its ID and space.

**Get app details**
> Get the details for app ID `abc123def456`.

**Retire an app - recycle bin missing (should be blocked)**
> Delete the app called "Test App DO NOT USE".
> *(Pre-condition: "Recycle Bin" space does not exist yet. Expected: tool refuses and explains the space must be created.)*

**Retire an app - happy path**
> Delete the app called "Test App DO NOT USE".
> *(Pre-condition: "Recycle Bin" space exists. Expected: app is moved, not hard-deleted.)*

---

## Spaces

**List all spaces**
> List all spaces in my Qlik Cloud tenant, including their type and ID.

**Find a shared space by name**
> Find the space called "Finance" and return its ID and type.

**Create a shared space**
> Create a new shared space called "MCP Test Space".

**Create a managed space**
> Create a new managed space called "MCP Managed Demo".

**Delete a space by name (should be blocked)**
> Delete the space called "MCP Test Space". Look up its ID first if needed.
> *(Expected: tool blocks the operation and directs to the Management Console.)*

---

## Space Members

**List members of a space**
> List all members of the space called "Finance", including their roles.

**Add a user to a space by email**
> Add the user with email `john.doe@example.com` as a contributor to the space called "MCP Test Space".

**Change a member's role**
> Change the role of user `john.doe@example.com` in the "MCP Test Space" space from contributor to consumer.

**Remove a member from a space**
> Remove user `john.doe@example.com` from the space called "MCP Test Space".

---

## Users

**Get current user info**
> Who am I? Show my user profile from Qlik Cloud.

**List users in the tenant**
> List the first 10 users in the Qlik Cloud tenant.

**Find a user by email**
> Find the Qlik Cloud user with email `john.doe@example.com` and return their user ID.

---

## Reload Tasks

**List reloads**
> List the most recent 5 app reload tasks in Qlik Cloud.

**Trigger a reload**
> Trigger a reload for the app called "Sales Overview". Find its ID first if needed.

---

## Assistants

**List available assistants**
> List all Qlik Answers assistants available in my tenant.

**Ask a question (first turn)**
> Ask the assistant with ID `abc123` what the total sales were last quarter.
> *(Expected: response includes the answer and a thread_id.)*

**Continue a conversation (follow-up)**
> Using thread `xyz789`, ask the same assistant to break that down by region.
> *(Expected: response uses context from the previous turn.)*

---

## Create App from Data Product

**Create app - DataFiles source, happy path**
> Create a Qlik app called "ADIF Punctuality" from the data product named "ADIF Demo".
> *(Expected: app created, script set with LOAD FROM lib:// statements for each CSV dataset.)*

**Create app - connection-based source, connection name provided**
> Create a Qlik app called "Calidad Servicio" from the data product named "Calidad del Servicio", using connection name "Attunity_IOT.snowflakecomputing.com".
> *(Expected: app created, script set with LIB CONNECT TO + LOAD/SELECT blocks grouped by connection.)*

**Create app - connection-based source, connection name omitted**
> Create a Qlik app called "Calidad Servicio" from the data product named "Calidad del Servicio".
> *(Expected: Claude asks for the connection name before proceeding.)*

**Create app - ambiguous data product name**
> Create a Qlik app called "Test" from the data product named "Sales".
> *(Expected: if multiple matches, tool returns the list and asks for the ID.)*

**Create app - data product not found**
> Create a Qlik app called "Test" from the data product named "this does not exist".
> *(Expected: clear error, no app created.)*

---

## Error and Edge Cases

**Non-existent resource**
> Get details for the Qlik Cloud app with ID `doesnotexist000`.

**Invalid path**
> Call GET v1/thisdoesnotexist and show me what Qlik returns.

**Malformed body (tests JSON validation in server.py)**
> Create a space using this body: `{name: "bad json", type: shared}` (intentionally unquoted - verify the server rejects it cleanly before sending).
