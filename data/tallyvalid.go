// Intended for AI to figure out validation
func (self *Tally) CheckValid() error {
	if self.EventID == "" {
		return errors.New("tally-event-id-empty")
	}

	err := self.Time.CheckValid()
	if err != nil {
		return fmt.Errorf("tally-time-invalid: %w", err)
	}

	// Note: journal ID can be empty because not all
	// tallies are from journal entries.
	if self.Name == "" {
		return errors.New("tally-name-empty")
	}
	if strings.ToLower(self.Name) != self.Name {
		return errors.New("tally-name-not-lower-case")
	}
	// Use "self" to denote the user herself.
	if self.Who == "" {
		return errors.New("tally-who-empty")
	}
	if self.Unit == "" && self.Category == "" {
		return errors.New("tally-unit-and-category-empty")
	}
	if strings.ToLower(self.Unit) != self.Unit {
		return errors.New("tally-unit-not-lower-case")
	}

	// This is the largest value that is guaranteed to be the same for
	// float32 and int. Should be good enough for tallies anyway.
	if self.Value > 16777216 {
		return errors.New("tally-too-large")
	}
	if self.Value < 0 {
		return errors.New("tally-negative")
	}
	return nil
}
