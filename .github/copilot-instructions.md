## Development Guidelines

### Adding New Features
1. **New Pages**: Create in `fad/app/pages/` and register in `main.py` navigation
2. **New Components**: Add to `fad/app/components/` for reusable UI elements
3. **New Services**: Business logic goes in `fad/app/services/`
4. **New Scrapers**: Add provider support in `fad/scraper/scrapers.py`

### Database Changes
- Update table enums in `naming_conventions.py`
- Create/modify repositories in `data_access/`
- Update corresponding services
- Add migration logic if needed

### Testing
- Use pytest with custom markers
- Mark sensitive tests that require internet access with `@pytest.mark.sensitive`
- Mock external dependencies in unit tests
- Test scrapers separately from business logic

### Dependencies
- Use Poetry for dependency management
- Pin exact versions for stability
- Keep dev dependencies separate
- Python 3.12+ required

## Clean Code Guidelines

### Code Comments & Documentation
- **Avoid obvious comments** that just restate what the code does
- **No "change log" comments** explaining what was modified or when
- **Focus on WHY, not WHAT** - explain business logic and complex decisions
- **Remove TODO comments** once tasks are completed
- **Use meaningful variable/function names** instead of explaining with comments
- **Document complex algorithms** and non-obvious business rules only
- **Keep docstrings concise** and focused on usage, not implementation details

### Code Quality
- Prefer self-documenting code over comments
- Remove dead/commented-out code
- Eliminate redundant imports and variables
- Use type hints consistently
- Keep functions focused and single-purpose

## Common Tasks & Patterns

### Adding a New Financial Provider
1. Add provider name to appropriate list in `naming_conventions.py`
2. Create scraper class inheriting from base scraper
3. Implement required scraping methods
4. Add factory method in `get_scraper()`
5. Update credentials configuration
6. Add tests

### Creating New Analysis Features
1. Add service method for data processing
2. Create repository methods if new queries needed
3. Build Streamlit components for UI
4. Add plotting utilities in `utils/plotting.py`
5. Create new page or add to existing page

### Data Categorization & Tagging
- Use rule-based tagging system
- Categories defined in enums
- Support for manual overrides
- Split transaction capability

## Security & Credentials
- Credentials stored in YAML files (not in git)
- 2FA automation support built-in
- Sensitive data handling in scrapers
- Use environment variables for production

## UI/UX Guidelines
- Follow Streamlit best practices
- Use streamlit-antd-components for enhanced UI
- Maintain consistent layout across pages
- Support wide layout mode
- Provide clear navigation structure
- **Always use unique keys for widgets**: Every Streamlit widget (st.selectbox, st.button, st.text_input, etc.) must have a unique `key` parameter

## Error Handling
- Custom exception hierarchy in `scraper/exceptions.py`
- Specific error types: LoginError, CredentialsError, TimeoutError, etc.
- Graceful degradation for scraping failures
- User-friendly error messages in UI

## Performance Considerations
- Use pandas for data processing
- SQLite with proper indexing
- Lazy loading for large datasets
- Background processing for scraping operations

## Documentation Standards
- Use Google-style docstrings
- Document all public methods
- Include type hints
- Update README for major changes

## Future Features (TODOs)
- mark multiple rows when tagging transactions
- update data after adding a new rule (apply rule at creation)
- manually add transactions (cash, etc.)
- rearrange app layout to be more intuitive
- User authentication system
- Multi-user support with shared accounts
- Forecasting capabilities
- PDF salary slip processing
- Enhanced data visualization

When working on this project, always consider the layered architecture, follow the repository pattern for data access, and maintain the separation between UI components, business logic, and data access layers.
